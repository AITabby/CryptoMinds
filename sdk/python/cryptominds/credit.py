"""
SACRED 信用分客户端

五维信用分评估：Security, Availability, Consistency, Reliability, Economic
"""

from typing import Dict, Optional
import requests


class CreditClient:
    """SACRED 信用分查询客户端"""

    def __init__(self, base_url: str = "https://api.cryptominds.ai"):
        self.base_url = base_url

    def get_score(self, address: str) -> Dict:
        """
        查询 Agent 信用分

        Args:
            address: Agent 钱包地址

        Returns:
            {
                "address": "0x...",
                "score": 85,
                "grade": "AA",
                "dimensions": {
                    "security": 90,
                    "availability": 85,
                    "consistency": 80,
                    "reliability": 88,
                    "economic": 82
                }
            }
        """
        resp = requests.get(f"{self.base_url}/api/v1/credit/{address}")
        resp.raise_for_status()
        return resp.json()

    def get_history(self, address: str, limit: int = 10) -> Dict:
        """查询信用分历史变化"""
        resp = requests.get(
            f"{self.base_url}/api/v1/credit/{address}/history",
            params={"limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    def get_ranking(self, dimension: Optional[str] = None, limit: int = 100) -> Dict:
        """
        查询信用分排行榜

        Args:
            dimension: 可选，按特定维度排序 (security/availability/consistency/reliability/economic)
            limit: 返回数量
        """
        params = {"limit": limit}
        if dimension:
            params["dimension"] = dimension

        resp = requests.get(f"{self.base_url}/api/v1/credit/ranking", params=params)
        resp.raise_for_status()
        return resp.json()
