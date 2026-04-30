"""
结算通道抽象基类

所有结算通道（BSC、ETH、SOL、Lightning、Mock 等）都实现这个接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import time
import hashlib


@dataclass
class PaymentRequest:
    """支付请求"""
    channel_id: str
    chain: str
    token: str
    from_address: str
    to_address: str
    amount: Decimal
    order_id: str
    nonce: str = field(default_factory=lambda: hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:16])
    timestamp: int = field(default_factory=lambda: int(time.time()))
    description: str = ""
    extra: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "chain": self.chain,
            "token": self.token,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": str(self.amount),
            "order_id": self.order_id,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "description": self.description,
            "extra": self.extra,
        }

    def to_sign_message(self) -> str:
        """构造待签名消息"""
        import json
        data = self.to_dict()
        data.pop("timestamp", None)
        data.pop("extra", None)
        return json.dumps(data, sort_keys=True)


@dataclass
class PaymentResult:
    """支付结果"""
    success: bool
    tx_hash: str = ""
    channel_id: str = ""
    chain: str = ""
    token: str = ""
    from_address: str = ""
    to_address: str = ""
    amount: Decimal = Decimal("0")
    order_id: str = ""
    nonce: str = ""
    signature: str = ""
    block_number: int = 0
    proof: Dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "tx_hash": self.tx_hash,
            "channel_id": self.channel_id,
            "chain": self.chain,
            "token": self.token,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": str(self.amount),
            "order_id": self.order_id,
            "nonce": self.nonce,
            "signature": self.signature,
            "block_number": self.block_number,
            "proof": self.proof,
            "error": self.error,
        }


@dataclass
class EscrowResult:
    """托管结果"""
    success: bool
    escrow_id: str = ""
    tx_hash: str = ""
    amount: Decimal = Decimal("0")
    error: str = ""


class SettlementChannel(ABC):
    """
    结算通道抽象基类

    每个通道代表一种支付方式：
    - BSCNativeChannel: BSC 链 BNB 原生转账
    - ETHNativeChannel: ETH 链 ETH 原生转账
    - SOLNativeChannel: Solana 链 SOL 原生转账
    - MockChannel: 内存模拟（测试用）

    通道可以支持：
    - 直接支付（点对点转账）
    - 托管支付（先锁定，条件满足后释放）
    """

    channel_id: str = ""
    chain: str = ""
    token: str = ""
    decimals: int = 18
    supports_escrow: bool = False

    # ── 查询 ─────────────────────────────────────────

    @abstractmethod
    def get_balance(self, address: str) -> Decimal:
        """查询地址余额"""
        pass

    @abstractmethod
    def is_address_valid(self, address: str) -> bool:
        """验证地址格式"""
        pass

    # ── 直接支付 ─────────────────────────────────────

    @abstractmethod
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
        pass

    @abstractmethod
    def sign_payment(self, request: PaymentRequest, private_key: str) -> str:
        """签名支付请求"""
        pass

    @abstractmethod
    def execute_payment(
        self,
        request: PaymentRequest,
        signature: str,
        private_key: str
    ) -> PaymentResult:
        """执行支付"""
        pass

    @abstractmethod
    def verify_payment(self, result: PaymentResult) -> Tuple[bool, str]:
        """验证支付结果"""
        pass

    # ── 托管支付（可选）─────────────────────────────

    def escrow_lock(
        self,
        buyer_address: str,
        seller_address: str,
        amount: Decimal,
        order_id: str,
        timeout_seconds: int = 1800,
        **kwargs
    ) -> EscrowResult:
        """
        锁定资金到托管

        子类如果支持托管，需要重写此方法
        """
        return EscrowResult(success=False, error="此通道不支持托管")

    def escrow_release(
        self,
        escrow_id: str,
        to_address: str,
        private_key: str
    ) -> EscrowResult:
        """
        释放托管资金

        子类如果支持托管，需要重写此方法
        """
        return EscrowResult(success=False, error="此通道不支持托管")

    def escrow_refund(
        self,
        escrow_id: str,
        to_address: str,
        private_key: str
    ) -> EscrowResult:
        """
        退款托管资金

        子类如果支持托管，需要重写此方法
        """
        return EscrowResult(success=False, error="此通道不支持托管")

    # ── 元信息 ───────────────────────────────────────

    def to_dict(self) -> Dict:
        """返回通道信息"""
        return {
            "channel_id": self.channel_id,
            "chain": self.chain,
            "token": self.token,
            "decimals": self.decimals,
            "supports_escrow": self.supports_escrow,
        }
