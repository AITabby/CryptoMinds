"""
CryptoMinds API 客户端
"""

import requests
from typing import Dict, List, Optional


class CryptoMindsClient:
    """CryptoMinds API 客户端"""

    def __init__(
        self,
        api_url: str = "http://localhost:3458",
        api_key: Optional[str] = None,
    ):
        """
        初始化客户端

        Args:
            api_url: API基础URL
            api_key: API密钥（可选）
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-CryptoMinds-API-Key"] = api_key

    def get_credit_score(self, agent_id: str) -> Dict:
        """
        查询信用分

        Args:
            agent_id: Agent ID或钱包地址

        Returns:
            {
                "agent_id": "agent_001",
                "wallet": "0x...",
                "total_score": 850.5,
                "grade": "AAA",
                "dimensions": {...},
                "snapshot_hash": "abc123...",
                "calculated_at": 1234567890
            }
        """
        resp = self._session.get(f"{self.api_url}/api/v1/credit/{agent_id}")
        resp.raise_for_status()
        return resp.json()

    def get_records(self, agent_id: str, limit: int = 1000) -> List[Dict]:
        """
        获取履约记录

        Args:
            agent_id: Agent ID
            limit: 最大记录数

        Returns:
            履约记录列表
        """
        resp = self._session.get(
            f"{self.api_url}/api/v1/credit/{agent_id}/records",
            params={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("records", [])

    def get_verification_data(self, agent_id: str) -> Dict:
        """
        获取验证数据（信用分 + 履约记录）

        Args:
            agent_id: Agent ID

        Returns:
            {
                "score": {...},
                "records": [...],
                "agent_info": {...},
                "credit_data": {...}
            }
        """
        resp = self._session.get(f"{self.api_url}/api/v1/credit/{agent_id}/verify")
        resp.raise_for_status()
        return resp.json()

    def get_ranking(self, limit: int = 100) -> List[Dict]:
        """
        获取排行榜

        Args:
            limit: 最大数量

        Returns:
            排行榜列表
        """
        resp = self._session.get(
            f"{self.api_url}/api/v1/credit/ranking",
            params={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("ranking", [])

    def submit_record(self, record: Dict) -> Dict:
        """
        上报履约记录

        Args:
            record: 履约记录数据

        Returns:
            {
                "ok": True,
                "record_id": "rec_001",
                "credit_score": 850.5,
                "credit_grade": "AAA"
            }
        """
        resp = self._session.post(
            f"{self.api_url}/api/v1/records",
            json=record,
        )
        resp.raise_for_status()
        return resp.json()
