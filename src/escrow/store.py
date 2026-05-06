"""
Escrow 存储层

简化的托管存储，用于 API 服务。
"""

import json
import os
import time
import uuid
from typing import Dict, List, Optional

# 数据库路径
DB_PATH = os.getenv("CRYPTOMINDS_DB_PATH", "escrow.db")


class EscrowStore:
    """托管存储"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._escrows: Dict[str, Dict] = self._load()

    def _load(self) -> Dict:
        """加载托管数据"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        """保存托管数据"""
        with open(self.db_path, "w") as f:
            json.dump(self._escrows, f, indent=2, default=str)

    def create(
        self,
        buyer: str,
        seller: str,
        amount: float,
        token: str = "BNB",
        timeout: int = 86400,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """创建托管"""
        escrow_id = f"escrow_{uuid.uuid4().hex[:12]}"
        now = int(time.time())

        escrow = {
            "escrow_id": escrow_id,
            "buyer": buyer,
            "seller": seller,
            "amount": amount,
            "token": token,
            "timeout": timeout,
            "state": "created",
            "created_at": now,
            "metadata": metadata or {},
        }

        self._escrows[escrow_id] = escrow
        self._save()
        return escrow

    def get(self, escrow_id: str) -> Optional[Dict]:
        """获取托管"""
        return self._escrows.get(escrow_id)

    def fund(self, escrow_id: str, tx_hash: str) -> Optional[Dict]:
        """确认资金托管"""
        escrow = self._escrows.get(escrow_id)
        if not escrow or escrow["state"] != "created":
            return None

        escrow["state"] = "funded"
        escrow["funded_at"] = int(time.time())
        escrow["fund_tx_hash"] = tx_hash
        self._save()
        return escrow

    def deliver(self, escrow_id: str, proof: Dict) -> Optional[Dict]:
        """提交交付证明"""
        escrow = self._escrows.get(escrow_id)
        if not escrow or escrow["state"] != "funded":
            return None

        escrow["state"] = "delivered"
        escrow["delivered_at"] = int(time.time())
        escrow["delivery_proof"] = proof
        self._save()
        return escrow

    def release(self, escrow_id: str) -> Optional[Dict]:
        """释放资金"""
        escrow = self._escrows.get(escrow_id)
        if not escrow or escrow["state"] not in ("delivered", "verified"):
            return None

        escrow["state"] = "released"
        escrow["released_at"] = int(time.time())
        self._save()
        return escrow

    def refund(self, escrow_id: str) -> Optional[Dict]:
        """退款"""
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            return None

        # 允许退款的场景：卖家超时、仲裁买家胜诉
        allowed_states = ("funded", "disputed", "arbitrating")
        if escrow["state"] not in allowed_states:
            # 检查是否超时
            if escrow["state"] == "created":
                now = int(time.time())
                if now - escrow["created_at"] > escrow["timeout"]:
                    pass  # 允许退款
                else:
                    return None
            else:
                return None

        escrow["state"] = "refunded"
        escrow["refunded_at"] = int(time.time())
        self._save()
        return escrow

    def dispute(self, escrow_id: str, reason: str) -> Optional[Dict]:
        """发起争议"""
        escrow = self._escrows.get(escrow_id)
        if not escrow or escrow["state"] not in ("delivered", "funded"):
            return None

        escrow["state"] = "disputed"
        escrow["disputed_at"] = int(time.time())
        escrow["dispute_reason"] = reason
        self._save()
        return escrow

    def list_by_state(self, state: str) -> List[Dict]:
        """按状态列出托管"""
        return [e for e in self._escrows.values() if e["state"] == state]

    def list_by_buyer(self, buyer: str) -> List[Dict]:
        """按买家列出托管"""
        return [e for e in self._escrows.values() if e["buyer"] == buyer]

    def list_by_seller(self, seller: str) -> List[Dict]:
        """按卖家列出托管"""
        return [e for e in self._escrows.values() if e["seller"] == seller]
