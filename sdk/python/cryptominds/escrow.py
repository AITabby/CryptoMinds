"""
托管客户端

链上资金安全保障，11 态状态机管理。
"""

from typing import Dict, Optional
from enum import Enum
import requests


class EscrowState(Enum):
    """托管状态"""
    CREATED = "created"
    FUNDED = "funded"
    DELIVERED = "delivered"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    ARBITRATING = "arbitrating"
    RELEASED = "released"
    REFUNDED = "refunded"
    SLASHED = "slashed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class EscrowClient:
    """托管客户端"""

    def __init__(self, base_url: str = "https://api.cryptominds.ai"):
        self.base_url = base_url

    def create(
        self,
        buyer: str,
        seller: str,
        amount: float,
        token: str = "BNB",
        timeout: int = 86400,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        创建托管

        Args:
            buyer: 买家地址
            seller: 卖家地址
            amount: 托管金额
            token: 代币类型 (BNB/BUSD/USDT)
            timeout: 超时时间（秒）
            metadata: 附加数据

        Returns:
            {"escrow_id": "0x...", "state": "created", ...}
        """
        payload = {
            "buyer": buyer,
            "seller": seller,
            "amount": amount,
            "token": token,
            "timeout": timeout,
        }
        if metadata:
            payload["metadata"] = metadata

        resp = requests.post(f"{self.base_url}/api/v1/escrow/create", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get(self, escrow_id: str) -> Dict:
        """查询托管状态"""
        resp = requests.get(f"{self.base_url}/api/v1/escrow/{escrow_id}")
        resp.raise_for_status()
        return resp.json()

    def fund(self, escrow_id: str, tx_hash: str) -> Dict:
        """确认资金已托管（买家调用）"""
        resp = requests.post(
            f"{self.base_url}/api/v1/escrow/{escrow_id}/fund",
            json={"tx_hash": tx_hash}
        )
        resp.raise_for_status()
        return resp.json()

    def deliver(self, escrow_id: str, proof: Dict) -> Dict:
        """提交交付证明（卖家调用）"""
        resp = requests.post(
            f"{self.base_url}/api/v1/escrow/{escrow_id}/deliver",
            json={"proof": proof}
        )
        resp.raise_for_status()
        return resp.json()

    def confirm(self, escrow_id: str) -> Dict:
        """确认交付，释放资金（买家调用）"""
        resp = requests.post(f"{self.base_url}/api/v1/escrow/{escrow_id}/release")
        resp.raise_for_status()
        return resp.json()

    def refund(self, escrow_id: str) -> Dict:
        """申请退款（买家调用，需满足条件）"""
        resp = requests.post(f"{self.base_url}/api/v1/escrow/{escrow_id}/refund")
        resp.raise_for_status()
        return resp.json()
