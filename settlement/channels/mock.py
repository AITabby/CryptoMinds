"""
Mock 通道 - 内存模拟

用于开发和测试，不需要真实区块链。
"""

import hashlib
import threading
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple

from ..base import SettlementChannel, PaymentRequest, PaymentResult, EscrowResult


class MockChannel(SettlementChannel):
    """
    内存模拟通道

    channel_id: mock
    chain: mock
    token: mock-token
    supports_escrow: True

    所有交易都在内存中模拟，适合：
    - 单元测试
    - 本地开发
    - Demo 演示
    """

    channel_id = "mock"
    chain = "mock"
    token = "mock-token"
    decimals = 18
    supports_escrow = True

    def __init__(self):
        # 内存余额表
        self._balances: Dict[str, Decimal] = {}
        # Lock for escrow state transitions to prevent race conditions
        self._escrow_lock = threading.Lock()
        # 内存托管表
        self._escrows: Dict[str, Dict] = {}
        # 交易历史
        self._transactions: list = []

    # ── 余额管理（测试用）───────────────────────────

    def set_balance(self, address: str, amount: Decimal) -> None:
        """设置地址余额（测试用）"""
        self._balances[address.lower()] = amount

    def mint(self, address: str, amount: Decimal) -> None:
        """给地址增加余额（测试用）"""
        addr = address.lower()
        self._balances[addr] = self._balances.get(addr, Decimal("0")) + amount

    def burn(self, address: str, amount: Decimal) -> bool:
        """减少地址余额（测试用）"""
        addr = address.lower()
        if self._balances.get(addr, Decimal("0")) >= amount:
            self._balances[addr] -= amount
            return True
        return False

    # ── 查询 ─────────────────────────────────────────

    def get_balance(self, address: str) -> Decimal:
        """查询余额"""
        return self._balances.get(address.lower(), Decimal("0"))

    def is_address_valid(self, address: str) -> bool:
        """验证地址格式（Mock 总是返回 True）"""
        return len(address) > 0

    # ── 直接支付 ─────────────────────────────────────

    def create_payment(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        order_id: str,
        description: str = "",
        **kwargs
    ) -> PaymentRequest:
        """创建支付请求"""
        return PaymentRequest(
            channel_id=self.channel_id,
            chain=self.chain,
            token=self.token,
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            order_id=order_id,
            description=description,
            extra=kwargs,
        )

    def sign_payment(self, request: PaymentRequest, private_key: str) -> str:
        """签名支付请求（Mock 返回假签名）"""
        return hashlib.sha256(
            f"{request.order_id}{request.nonce}{private_key}".encode()
        ).hexdigest()

    def execute_payment(
        self,
        request: PaymentRequest,
        signature: str,
        private_key: str
    ) -> PaymentResult:
        """执行支付（内存转账）"""

        from_addr = request.from_address.lower()
        to_addr = request.to_address.lower()
        amount = request.amount

        # 检查余额
        if self._balances.get(from_addr, Decimal("0")) < amount:
            return PaymentResult(
                success=False,
                error="余额不足",
                channel_id=self.channel_id,
                order_id=request.order_id,
            )

        # 执行转账
        self._balances[from_addr] -= amount
        self._balances[to_addr] = self._balances.get(to_addr, Decimal("0")) + amount

        # 生成假交易哈希
        tx_hash = "0x" + hashlib.sha256(
            f"{time.time()}{from_addr}{to_addr}{amount}".encode()
        ).hexdigest()[:64]

        # 记录交易
        self._transactions.append({
            "tx_hash": tx_hash,
            "from": from_addr,
            "to": to_addr,
            "amount": str(amount),
            "order_id": request.order_id,
            "timestamp": time.time(),
        })

        return PaymentResult(
            success=True,
            tx_hash=tx_hash,
            channel_id=self.channel_id,
            chain=self.chain,
            token=self.token,
            from_address=request.from_address,
            to_address=request.to_address,
            amount=amount,
            order_id=request.order_id,
            nonce=request.nonce,
            signature=signature,
            block_number=len(self._transactions),
            proof={"mock": True},
        )

    def verify_payment(self, result: PaymentResult) -> Tuple[bool, str]:
        """验证支付结果"""
        # 在交易历史中查找
        for tx in self._transactions:
            if tx["tx_hash"] == result.tx_hash:
                return True, "支付验证通过"
        return False, "交易不存在"

    # ── 托管支付 ─────────────────────────────────────

    def escrow_lock(
        self,
        buyer_address: str,
        seller_address: str,
        amount: Decimal,
        order_id: str,
        timeout_seconds: int = 1800,
        **kwargs
    ) -> EscrowResult:
        """锁定资金到托管"""

        buyer_addr = buyer_address.lower()
        seller_addr = seller_address.lower()

        # 检查余额
        if self._balances.get(buyer_addr, Decimal("0")) < amount:
            return EscrowResult(
                success=False,
                error="余额不足",
            )

        # 锁定资金
        self._balances[buyer_addr] -= amount

        # 创建托管记录
        escrow_id = hashlib.sha256(f"{order_id}{time.time()}".encode()).hexdigest()[:32]
        self._escrows[escrow_id] = {
            "buyer": buyer_addr,
            "seller": seller_addr,
            "amount": amount,
            "order_id": order_id,
            "locked_at": time.time(),
            "timeout": timeout_seconds,
            "status": "locked",
        }

        return EscrowResult(
            success=True,
            escrow_id=escrow_id,
            amount=amount,
        )

    def escrow_release(
        self,
        escrow_id: str,
        to_address: str,
        private_key: str = "",
    ) -> EscrowResult:
        """释放托管资金给卖家"""
        with self._escrow_lock:
            escrow = self._escrows.get(escrow_id)
            if not escrow:
                return EscrowResult(success=False, error="托管记录不存在")

            if escrow["status"] != "locked":
                return EscrowResult(success=False, error=f"托管状态错误: {escrow['status']}")

            # 释放资金
            to_addr = to_address.lower()
            self._balances[to_addr] = self._balances.get(to_addr, Decimal("0")) + escrow["amount"]
            escrow["status"] = "released"

        tx_hash = "0x" + hashlib.sha256(f"{escrow_id}{time.time()}".encode()).hexdigest()[:64]

        return EscrowResult(
            success=True,
            escrow_id=escrow_id,
            tx_hash=tx_hash,
            amount=escrow["amount"],
        )

    def escrow_refund(
        self,
        escrow_id: str,
        to_address: str,
        private_key: str = "",
    ) -> EscrowResult:
        """退款给买家"""
        with self._escrow_lock:
            escrow = self._escrows.get(escrow_id)
            if not escrow:
                return EscrowResult(success=False, error="托管记录不存在")

            if escrow["status"] != "locked":
                return EscrowResult(success=False, error=f"托管状态错误: {escrow['status']}")

            # 退款给买家
            buyer_addr = escrow["buyer"]
            self._balances[buyer_addr] = self._balances.get(buyer_addr, Decimal("0")) + escrow["amount"]
            escrow["status"] = "refunded"

        tx_hash = "0x" + hashlib.sha256(f"{escrow_id}{time.time()}".encode()).hexdigest()[:64]

        return EscrowResult(
            success=True,
            escrow_id=escrow_id,
            tx_hash=tx_hash,
            amount=escrow["amount"],
        )

    # ── 测试辅助 ─────────────────────────────────────

    def get_transactions(self) -> list:
        """获取所有交易记录（测试用）"""
        return self._transactions.copy()

    def get_escrows(self) -> Dict:
        """获取所有托管记录（测试用）"""
        return self._escrows.copy()

    def reset(self) -> None:
        """重置所有状态（测试用）"""
        self._balances.clear()
        self._escrows.clear()
        self._transactions.clear()
