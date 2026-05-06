"""
仲裁客户端

信誉加权仲裁，三分支验证。
"""

from typing import Dict, Optional
import requests


class ArbitrationClient:
    """仲裁客户端"""

    def __init__(self, base_url: str = "https://api.cryptominds.ai"):
        self.base_url = base_url

    def submit(
        self,
        escrow_id: str,
        reason: str,
        evidence: Optional[Dict] = None
    ) -> Dict:
        """
        提交争议

        Args:
            escrow_id: 托管 ID
            reason: 争议原因
            evidence: 证据数据

        Returns:
            {"dispute_id": "0x...", "state": "pending", ...}
        """
        payload = {"escrow_id": escrow_id, "reason": reason}
        if evidence:
            payload["evidence"] = evidence

        resp = requests.post(f"{self.base_url}/api/v1/arbitrate/submit", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get(self, dispute_id: str) -> Dict:
        """查询争议状态"""
        resp = requests.get(f"{self.base_url}/api/v1/arbitrate/{dispute_id}")
        resp.raise_for_status()
        return resp.json()

    def add_evidence(self, dispute_id: str, evidence: Dict) -> Dict:
        """添加证据"""
        resp = requests.post(
            f"{self.base_url}/api/v1/arbitrate/{dispute_id}/evidence",
            json=evidence
        )
        resp.raise_for_status()
        return resp.json()

    def get_arbitrators(self, dispute_id: str) -> Dict:
        """查询仲裁员列表"""
        resp = requests.get(f"{self.base_url}/api/v1/arbitrate/{dispute_id}/arbitrators")
        resp.raise_for_status()
        return resp.json()
