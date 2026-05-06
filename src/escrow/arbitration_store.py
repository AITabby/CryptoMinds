"""
仲裁存储层

简化的仲裁存储，用于 API 服务。
"""

import json
import os
import time
import uuid
from typing import Dict, List, Optional

# 数据库路径
DB_PATH = os.getenv("ARBITRATION_DB_PATH", "arbitration.db")


class ArbitrationStore:
    """仲裁存储"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._disputes: Dict[str, Dict] = self._load()

    def _load(self) -> Dict:
        """加载争议数据"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        """保存争议数据"""
        with open(self.db_path, "w") as f:
            json.dump(self._disputes, f, indent=2, default=str)

    def create(
        self,
        escrow_id: str,
        reason: str,
        evidence: Optional[Dict] = None
    ) -> Dict:
        """创建争议"""
        dispute_id = f"dispute_{uuid.uuid4().hex[:12]}"
        now = int(time.time())

        dispute = {
            "dispute_id": dispute_id,
            "escrow_id": escrow_id,
            "reason": reason,
            "evidence": evidence or {},
            "state": "pending",
            "created_at": now,
            "arbitrators": [],
            "votes": [],
            "result": None,
        }

        self._disputes[dispute_id] = dispute
        self._save()
        return dispute

    def get(self, dispute_id: str) -> Optional[Dict]:
        """获取争议"""
        return self._disputes.get(dispute_id)

    def add_evidence(self, dispute_id: str, evidence: Dict) -> Optional[Dict]:
        """添加证据"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return None

        if "evidence_list" not in dispute:
            dispute["evidence_list"] = []

        evidence["added_at"] = int(time.time())
        dispute["evidence_list"].append(evidence)
        self._save()
        return dispute

    def get_arbitrators(self, dispute_id: str) -> List[Dict]:
        """获取仲裁员列表"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return []

        # 返回已分配的仲裁员，或返回空列表（实际场景中会根据信用分选择）
        return dispute.get("arbitrators", [])

    def assign_arbitrators(self, dispute_id: str, arbitrators: List[Dict]) -> Optional[Dict]:
        """分配仲裁员"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return None

        dispute["arbitrators"] = arbitrators
        dispute["state"] = "arbitrating"
        self._save()
        return dispute

    def vote(self, dispute_id: str, arbitrator: str, vote: str, weight: float) -> Optional[Dict]:
        """仲裁员投票"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return None

        vote_record = {
            "arbitrator": arbitrator,
            "vote": vote,  # "buyer" or "seller"
            "weight": weight,
            "voted_at": int(time.time()),
        }
        dispute["votes"].append(vote_record)
        self._save()
        return dispute

    def resolve(self, dispute_id: str, result: str, reason: str = "") -> Optional[Dict]:
        """解决争议"""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return None

        dispute["state"] = "resolved"
        dispute["result"] = result  # "buyer_wins", "seller_wins", "split"
        dispute["resolution_reason"] = reason
        dispute["resolved_at"] = int(time.time())
        self._save()
        return dispute

    def list_pending(self) -> List[Dict]:
        """列出待处理争议"""
        return [d for d in self._disputes.values() if d["state"] == "pending"]

    def list_by_escrow(self, escrow_id: str) -> List[Dict]:
        """按托管ID列出争议"""
        return [d for d in self._disputes.values() if d["escrow_id"] == escrow_id]
