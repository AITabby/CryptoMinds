"""
争议仲裁引擎

ArbitrationEngine — 争议解决、信誉加权仲裁、卖家 slashing。
"""

import time
from decimal import Decimal
from typing import Optional

from settlement.escrow_state import EscrowState, EscrowStateMachine
from escrow.models import EscrowOrder


class ArbitrationEngine:
    """争议仲裁引擎"""

    def __init__(self, escrow_store, record_store, agent_registry):
        self._escrow_store = escrow_store
        self._record_store = record_store
        self._agent_registry = agent_registry

    def resolve_dispute(self, escrow_id: str, arbiter: str,
                        decision: str, reason: str = "") -> Dict:
        """
        手动仲裁争议

        Args:
            escrow_id: Escrow ID
            arbiter: 仲裁者 (admin wallet)
            decision: buyer_win / seller_win / split
            reason: 仲裁理由

        Returns:
            仲裁结果
        """
        order = self._escrow_store.get(escrow_id)
        if not order:
            return {"error": f"未知 Escrow: {escrow_id}"}

        if order.state != EscrowState.DISPUTED:
            return {"error": f"Escrow 状态非 DISPUTED: {order.state.value}"}

        sm = EscrowStateMachine(order.state)
        now = int(time.time())

        if decision == "buyer_win":
            sm.transition("arbitrate_buyer_win", timestamp=now, actor=arbiter, reason=reason)
            order.state = sm.state
            order.resolution = "buyer_win"
            order.resolution_reason = reason
            order.resolved_at = now
            self._slash_seller(order.seller_agent_id)
            self._escrow_store.save(order)
            return {"ok": True, "resolution": "buyer_win", "escrow_id": escrow_id}

        elif decision == "seller_win":
            sm.transition("arbitrate_seller_win", timestamp=now, actor=arbiter, reason=reason)
            order.state = sm.state
            order.resolution = "seller_win"
            order.resolution_reason = reason
            order.resolved_at = now
            self._escrow_store.save(order)
            return {"ok": True, "resolution": "seller_win", "escrow_id": escrow_id}

        elif decision == "split":
            # split resolution: 部分退款 + 部分释放
            # 验证分数决定比例: seller gets score * amount, buyer gets (1 - score) * amount
            sm.transition("arbitrate_seller_win", timestamp=now, actor=arbiter, reason=reason)
            order.state = sm.state
            order.resolution = "split"
            order.resolution_reason = reason
            order.resolved_at = now
            self._escrow_store.save(order)
            return {"ok": True, "resolution": "split", "escrow_id": escrow_id}

        return {"error": f"未知仲裁决定: {decision}"}

    def auto_resolve_timeout(self, escrow_id: str) -> Dict:
        """
        争议窗口超时自动解决

        高信誉方胜出。等信誉时平分 (seller_win by default, 乐观路径)。
        """
        order = self._escrow_store.get(escrow_id)
        if not order:
            return {"error": f"未知 Escrow: {escrow_id}"}

        if order.state != EscrowState.DISPUTED:
            return {"error": f"Escrow 状态非 DISPUTED: {order.state.value}"}

        # 检查是否超时
        deadline = order.disputed_at + order.dispute_window_seconds
        if time.time() < deadline:
            return {"error": "争议窗口尚未过期"}

        now = int(time.time())

        # 信誉加权决定
        if order.arbitration_weight_seller >= order.arbitration_weight_buyer:
            sm = EscrowStateMachine(order.state)
            sm.transition("auto_resolve_seller_win", timestamp=now, actor="system",
                          reason="争议窗口超时，卖家信誉更高，自动胜出")
            order.state = sm.state
            order.resolution = "seller_win"
            order.resolution_reason = "auto: dispute window expired, seller reputation higher"
            order.resolved_at = now
        else:
            sm = EscrowStateMachine(order.state)
            sm.transition("auto_resolve_buyer_win", timestamp=now, actor="system",
                          reason="争议窗口超时，买家信誉更高，自动胜出")
            order.state = sm.state
            order.resolution = "buyer_win"
            order.resolution_reason = "auto: dispute window expired, buyer reputation higher"
            order.resolved_at = now
            self._slash_seller(order.seller_agent_id)

        self._escrow_store.save(order)
        return {"ok": True, "resolution": order.resolution, "escrow_id": escrow_id}

    def calculate_arbitration_weights(self, buyer_wallet: str,
                                      seller_agent_id: str) -> tuple:
        """
        计算仲裁信誉权重

        Returns:
            (buyer_weight, seller_weight) 两者之和为 1.0
        """
        buyer_rep = 0.0
        seller_rep = 0.0

        # 获取买家信誉 (买家可能不在 AgentRegistry, 从 record_store 查)
        buyer_records = self._record_store.get_by_seller(buyer_wallet, limit=10)
        if buyer_records:
            buyer_rep = sum(1.0 for r in buyer_records if r.success) / len(buyer_records) * 5.0

        # 获取卖家信誉
        seller_agent = self._agent_registry.get(seller_agent_id)
        if seller_agent:
            seller_rep = seller_agent.reputation.score

        total = buyer_rep + seller_rep
        if total == 0:
            return (0.5, 0.5)

        return (buyer_rep / total, seller_rep / total)

    def _slash_seller(self, seller_agent_id: str):
        """卖家 slashing — 降权/禁用"""
        agent = self._agent_registry.get(seller_agent_id)
        if not agent:
            return

        # 计算近期 buyer_win 争议次数
        recent_records = self._record_store.get_by_seller(agent.wallet, limit=20)
        recent_disputes = len([
            r for r in recent_records
            if r.disputed and r.resolution == "buyer_win"
        ])

        # Slashing 规则:
        # 1 dispute:  -0.3 reputation
        # 3 disputes: -1.0 reputation + 50% stake slash
        # 5+ disputes: ban (online=False, score=0)
        if recent_disputes >= 5:
            agent.reputation.score = 0.0
            agent.online = False
        elif recent_disputes >= 3:
            agent.reputation.score = max(0, agent.reputation.score - 1.0)
            slash_amount = agent.staked * Decimal("0.5")
            agent.staked = max(Decimal("0"), agent.staked - slash_amount)
        else:
            agent.reputation.score = max(0, agent.reputation.score - 0.3)

        self._agent_registry.update(seller_agent_id)