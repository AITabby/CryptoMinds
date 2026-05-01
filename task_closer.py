"""
任务闭环处理器

将验证层、结算层、争议层联动：
1. 任务执行完成 → 提交结果
2. 验证门验证 → 三分支判定:
   - 通过 + score >= threshold → 自动结算放款
   - 通过 + score < threshold → 进入争议窗口
   - 失败 → 进入争议窗口
3. 验证通过 → 结算放款
4. 记录履约 → 更新信誉
"""

import os
import json
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import logging

from protocol import (
    verify_task, record_task_completion, update_agent_reputation,
    ChannelRegistry, GateRegistry, AgentRegistry,
)
from verification.base import TaskInput, TaskOutput
from reputation.record import TaskStatus
from settlement.escrow_state import EscrowState

logger = logging.getLogger(__name__)

# Default verification threshold — below this score triggers dispute
DEFAULT_VERIFICATION_THRESHOLD = 0.7

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    success: bool
    verified: bool = False
    paid: bool = False
    disputed: bool = False
    amount: Decimal = Decimal("0")
    tx_hash: str = ""
    error: str = ""
    verification_score: float = 0.0
    escrow_id: str = ""


class TaskCloser:
    """
    任务闭环处理器

    负责：
    1. 验证任务结果 (三分支: pass/dispute-low/dispute-fail)
    2. 触发结算放款 or 进入争议
    3. 记录履约
    4. 更新信誉
    """

    def __init__(self, escrow_store=None, arbitration_engine=None):
        self.pending_escrows: Dict[str, Dict] = {}
        self._escrow_store = escrow_store
        self._arbitration_engine = arbitration_engine

    # ── 完整闭环 ─────────────────────────────────────

    def close_task(
        self,
        task_id: str,
        task_type: str,
        buyer_wallet: str,
        seller_wallet: str,
        seller_agent_id: str,
        chain: str,
        amount: Decimal,
        channel_id: str,
        task_output: TaskOutput,
        escrow_id: str = None,
        private_key: str = None,
        verification_threshold: float = DEFAULT_VERIFICATION_THRESHOLD,
    ) -> TaskResult:
        """
        完成任务闭环 (三分支逻辑)

        1. 验证结果
        2a. 验证通过 + score >= threshold → 结算放款
        2b. 验证通过 + score < threshold → 进入争议窗口
        2c. 验证失败 → 进入争议窗口
        3. 记录履约
        4. 更新信誉

        Args:
            task_id: 任务 ID
            task_type: 任务类型
            buyer_wallet: 买家钱包
            seller_wallet: 卖家钱包
            seller_agent_id: 卖家 Agent ID
            chain: 链
            amount: 金额
            channel_id: 结算通道 ID
            task_output: 任务输出
            escrow_id: 托管 ID（如果有）
            private_key: 卖家私钥（用于签名）
            verification_threshold: 验证分数阈值，低于此进入争议

        Returns:
            TaskResult
        """
        result = TaskResult(
            task_id=task_id,
            success=False,
            amount=amount,
        )

        # 1. 构造任务输入
        task_input = TaskInput(
            task_type=task_type,
            buyer_wallet=buyer_wallet,
            seller_wallet=seller_wallet,
            chain=chain,
            amount=amount,
        )

        # 2. 验证结果
        logger.info(f"[{task_id}] 开始验证...")
        verify_result = verify_task(task_type, task_input, task_output)
        result.verification_score = verify_result.score

        # ── 三分支判定 ──────────────────────────────────

        if not verify_result.success:
            # 分支 2c: 验证失败 → 争议窗口
            logger.warning(f"[{task_id}] 验证失败: {verify_result.error}")
            return self._enter_dispute(
                result=result,
                task_id=task_id,
                task_type=task_type,
                buyer_wallet=buyer_wallet,
                seller_wallet=seller_wallet,
                seller_agent_id=seller_agent_id,
                chain=chain,
                amount=amount,
                escrow_id=escrow_id,
                reason=f"验证失败: {verify_result.error}",
                initiator="system",
                verify_score=verify_result.score,
                evidence=verify_result.evidence,
            )

        # 验证通过，但检查分数阈值
        if verify_result.score < verification_threshold:
            # 分支 2b: 分数过低 → 争议窗口
            logger.warning(
                f"[{task_id}] 验证分数过低: {verify_result.score:.2f} < {verification_threshold}"
            )
            return self._enter_dispute(
                result=result,
                task_id=task_id,
                task_type=task_type,
                buyer_wallet=buyer_wallet,
                seller_wallet=seller_wallet,
                seller_agent_id=seller_agent_id,
                chain=chain,
                amount=amount,
                escrow_id=escrow_id,
                reason=f"验证分数过低: {verify_result.score:.2f} < {verification_threshold}",
                initiator="system",
                verify_score=verify_result.score,
                evidence=verify_result.evidence,
            )

        # 分支 2a: 验证通过 + 分数合格 → 自动结算
        result.verified = True
        logger.info(f"[{task_id}] 验证通过, 评分: {verify_result.score:.2f}")

        # 3. 结算放款
        logger.info(f"[{task_id}] 开始结算...")
        payment_result = self._settle_payment(
            channel_id=channel_id,
            escrow_id=escrow_id,
            seller_wallet=seller_wallet,
            amount=amount,
            private_key=private_key,
        )

        if payment_result["success"]:
            result.paid = True
            result.tx_hash = payment_result.get("tx_hash", "")
            logger.info(f"[{task_id}] 结算完成: {result.tx_hash[:20]}...")
        else:
            result.error = f"结算失败: {payment_result.get('error')}"
            logger.warning(f"[{task_id}] {result.error}")
            self._record_task(
                task_id=task_id,
                task_type=task_type,
                buyer_wallet=buyer_wallet,
                seller_wallet=seller_wallet,
                seller_agent_id=seller_agent_id,
                chain=chain,
                amount=amount,
                status=TaskStatus.SETTLEMENT_FAILED,
                score=verify_result.score,
                evidence={
                    **(verify_result.evidence or {}),
                    "settlement_error": payment_result.get("error", ""),
                },
            )
            return result

        # 4. 记录履约
        logger.info(f"[{task_id}] 记录履约...")
        self._record_task(
            task_id=task_id,
            task_type=task_type,
            buyer_wallet=buyer_wallet,
            seller_wallet=seller_wallet,
            seller_agent_id=seller_agent_id,
            chain=chain,
            amount=amount,
            status=TaskStatus.SETTLED,
            score=verify_result.score,
            payment_tx=result.tx_hash,
            payment_amount=amount if result.paid else Decimal("0"),
            evidence=verify_result.evidence,
        )

        # 5. 更新信誉
        logger.info(f"[{task_id}] 更新信誉...")
        update_agent_reputation(seller_agent_id)

        result.success = True
        return result

    # ── 争议入口 ────────────────────────────────────────

    def _enter_dispute(
        self,
        result: TaskResult,
        task_id: str,
        task_type: str,
        buyer_wallet: str,
        seller_wallet: str,
        seller_agent_id: str,
        chain: str,
        amount: Decimal,
        escrow_id: str = None,
        reason: str = "",
        initiator: str = "system",
        verify_score: float = 0.0,
        evidence: Dict = None,
    ) -> TaskResult:
        """进入争议窗口"""
        result.disputed = True
        result.verification_score = verify_score
        result.error = reason

        # 记录争议状态
        self._record_task(
            task_id=task_id,
            task_type=task_type,
            buyer_wallet=buyer_wallet,
            seller_wallet=seller_wallet,
            seller_agent_id=seller_agent_id,
            chain=chain,
            amount=amount,
            status=TaskStatus.DISPUTED,
            score=verify_score,
            evidence=evidence or {},
            disputed=True,
            dispute_reason=reason,
        )

        # 更新 EscrowOrder 状态 (如果 escrow_store 可用)
        if self._escrow_store and escrow_id:
            from escrow.models import EscrowOrder
            order = self._escrow_store.get(escrow_id)
            if order and order.state in (EscrowState.DELIVERED, EscrowState.VERIFIED):
                now = int(time.time())
                buyer_w, seller_w = self._calculate_arbitration_weights(
                    buyer_wallet, seller_agent_id
                )
                order.state = EscrowState.DISPUTED
                order.disputed_at = now
                order.dispute_reason = reason
                order.dispute_initiator = initiator
                order.verification_score = verify_score
                order.arbitration_weight_buyer = buyer_w
                order.arbitration_weight_seller = seller_w
                self._escrow_store.save(order)
                result.escrow_id = escrow_id

        # 更新信誉 (争议也影响评分)
        update_agent_reputation(seller_agent_id)

        logger.warning(f"[{task_id}] 进入争议窗口: {reason}")
        return result

    def _calculate_arbitration_weights(
        self, buyer_wallet: str, seller_agent_id: str
    ) -> Tuple[float, float]:
        """计算仲裁信誉权重"""
        buyer_rep = 0.0
        seller_rep = 0.0

        seller_agent = AgentRegistry.get(seller_agent_id)
        if seller_agent:
            seller_rep = seller_agent.reputation.score

        # 买家可能不在 AgentRegistry, 给基础信誉
        buyer_rep = 2.5  # 默认中等信誉

        total = buyer_rep + seller_rep
        if total == 0:
            return (0.5, 0.5)

        return (buyer_rep / total, seller_rep / total)

    # ── 结算 ─────────────────────────────────────────

    def _settle_payment(
        self,
        channel_id: str,
        escrow_id: str,
        seller_wallet: str,
        amount: Decimal,
        private_key: str,
    ) -> Dict:
        """
        结算放款

        如果有托管，释放托管资金。
        如果没有托管，说明是直接支付，跳过。
        """
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            return {"success": False, "error": f"未知通道: {channel_id}"}

        # 如果有托管 ID，释放托管
        if escrow_id:
            try:
                escrow_result = channel.escrow_release(
                    escrow_id=escrow_id,
                    to_address=seller_wallet,
                    private_key=private_key or "",
                )

                if escrow_result.success:
                    return {
                        "success": True,
                        "tx_hash": escrow_result.tx_hash,
                    }
                else:
                    return {
                        "success": False,
                        "error": escrow_result.error,
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # 没有托管，说明是直接支付（买家已直接转账）
        # 这种情况下不需要额外操作
        return {
            "success": True,
            "tx_hash": "direct_payment",
            "note": "直接支付，无需托管释放",
        }

    # ── 履约记录 ─────────────────────────────────────

    def _record_task(
        self,
        task_id: str,
        task_type: str,
        buyer_wallet: str,
        seller_wallet: str,
        seller_agent_id: str,
        chain: str,
        amount: Decimal,
        status: TaskStatus,
        score: float = 0,
        payment_tx: str = "",
        payment_amount: Decimal = Decimal("0"),
        evidence: Dict = None,
        disputed: bool = False,
        dispute_reason: str = "",
    ) -> None:
        """记录履约"""
        record_task_completion(
            task_id=task_id,
            task_type=task_type,
            buyer_wallet=buyer_wallet,
            seller_wallet=seller_wallet,
            seller_agent_id=seller_agent_id,
            chain=chain,
            amount=amount,
            status=status,
            score=score,
            payment_tx=payment_tx,
            payment_amount=payment_amount,
            evidence=evidence or {},
            disputed=disputed,
            dispute_reason=dispute_reason,
        )


# ── 托管管理 ────────────────────────────────────────

class EscrowManager:
    """
    托管管理器

    负责：
    1. 创建托管
    2. 查询托管状态
    3. 释放/退款托管
    """

    def __init__(self):
        self._escrows: Dict[str, Dict] = {}

    def create_escrow(
        self,
        buyer_wallet: str,
        seller_wallet: str,
        amount: Decimal,
        channel_id: str,
        task_id: str,
        timeout_seconds: int = 1800,
    ) -> Dict:
        """
        创建托管

        Args:
            buyer_wallet: 买家钱包
            seller_wallet: 卖家钱包
            amount: 金额
            channel_id: 结算通道
            task_id: 任务 ID
            timeout_seconds: 超时时间

        Returns:
            托管信息
        """
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            return {"error": f"未知通道: {channel_id}"}

        # 尝试创建托管
        if channel.supports_escrow:
            escrow_result = channel.escrow_lock(
                buyer_address=buyer_wallet,
                seller_address=seller_wallet,
                amount=amount,
                order_id=task_id,
                timeout_seconds=timeout_seconds,
            )

            if escrow_result.success:
                escrow_id = escrow_result.escrow_id
                self._escrows[escrow_id] = {
                    "escrow_id": escrow_id,
                    "task_id": task_id,
                    "buyer_wallet": buyer_wallet,
                    "seller_wallet": seller_wallet,
                    "amount": amount,
                    "channel_id": channel_id,
                    "status": "locked",
                    "created_at": int(time.time()),
                }

                return {
                    "ok": True,
                    "escrow_id": escrow_id,
                    "channel_id": channel_id,
                }
            else:
                return {"error": escrow_result.error}

        # 通道不支持托管
        return {"error": f"通道 {channel_id} 不支持托管"}

    def get_escrow(self, escrow_id: str) -> Optional[Dict]:
        """获取托管信息"""
        return self._escrows.get(escrow_id)

    def release_escrow(
        self,
        escrow_id: str,
        seller_wallet: str,
        channel_id: str,
        private_key: str,
    ) -> Dict:
        """释放托管"""
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            return {"error": f"未知通道: {channel_id}"}

        result = channel.escrow_release(
            escrow_id=escrow_id,
            to_address=seller_wallet,
            private_key=private_key,
        )

        if result.success:
            if escrow_id in self._escrows:
                self._escrows[escrow_id]["status"] = "released"

        return {
            "success": result.success,
            "tx_hash": result.tx_hash,
            "error": result.error,
        }

    def refund_escrow(
        self,
        escrow_id: str,
        buyer_wallet: str,
        channel_id: str,
        private_key: str,
    ) -> Dict:
        """退款托管"""
        channel = ChannelRegistry.get(channel_id)
        if not channel:
            return {"error": f"未知通道: {channel_id}"}

        result = channel.escrow_refund(
            escrow_id=escrow_id,
            to_address=buyer_wallet,
            private_key=private_key,
        )

        if result.success:
            if escrow_id in self._escrows:
                self._escrows[escrow_id]["status"] = "refunded"

        return {
            "success": result.success,
            "tx_hash": result.tx_hash,
            "error": result.error,
        }


# ── 全局实例 ────────────────────────────────────────

task_closer = TaskCloser()
escrow_manager = EscrowManager()


# ── 测试 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== 任务闭环测试 ===\n")

    # 注册一个测试 Agent
    from protocol import register_agent
    from agent.capability import AgentCapability, CapabilitySpec, ReputationInfo

    agent = AgentCapability(
        agent_id="test-seller",
        name="测试卖家",
        wallet="0xseller",
        capabilities=[
            CapabilitySpec(
                task_type="token_delivery",
                verification_gate="token_delivery",
                supported_chains=["mock"],
                supported_channels=["mock"],
                pricing_model="fixed",
                base_price=Decimal("0.001"),
            )
        ],
        staked=Decimal("10.0"),
    )
    register_agent(agent)

    # 创建任务输出
    task_output = TaskOutput(
        task_type="token_delivery",
        seller_wallet="0xseller",
        tx_hash="0xabc123",
        token_address="0xtoken",
        token_amount="1000000",
    )

    # 执行闭环
    result = task_closer.close_task(
        task_id="test-task-001",
        task_type="token_delivery",
        buyer_wallet="0xbuyer",
        seller_wallet="0xseller",
        seller_agent_id="test-seller",
        chain="mock",
        amount=Decimal("0.01"),
        channel_id="mock",
        task_output=task_output,
    )

    print("闭环结果:")
    print(json.dumps({
        "task_id": result.task_id,
        "success": result.success,
        "verified": result.verified,
        "paid": result.paid,
        "amount": str(result.amount),
        "tx_hash": result.tx_hash,
        "error": result.error,
    }, indent=2))
