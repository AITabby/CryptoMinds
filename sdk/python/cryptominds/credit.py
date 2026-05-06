"""
SACRED 信用分客户端

五维信用分评估：Stability, Activity, Creditworthiness, Reliability, Ecosystem
"""

from typing import Dict
import requests


class CreditClient:
    """SACRED 信用分查询客户端"""

    def __init__(self, base_url: str = "http://localhost:3458"):
        self.base_url = base_url

    def get_score(self, address: str) -> Dict:
        """
        查询 Agent 信用分

        Args:
            address: Agent 钱包地址或 Agent ID

        Returns:
            {
                "agent_id": "0x...",
                "wallet": "0x...",
                "total_score": 850,
                "grade": "AAA",
                "is_cold_start": false,
                "dimensions": {
                    "S": {"dimension": "S", "name": "Stability",
                          "score": 180, "max": 200, "components": {...}},
                    "A": {"dimension": "A", "name": "Activity",
                          "score": 170, "max": 200, "components": {...}},
                    "C": {"dimension": "C", "name": "Creditworthiness",
                          "score": 160, "max": 200, "components": {...}},
                    "R": {"dimension": "R", "name": "Reliability",
                          "score": 176, "max": 200, "components": {...}},
                    "E": {"dimension": "E", "name": "Ecosystem",
                          "score": 164, "max": 200, "components": {...}}
                },
                "calculated_at": 1715040000,
                "snapshot_hash": "abc123"
            }
        """
        resp = requests.get(f"{self.base_url}/api/v1/credit/{address}")
        resp.raise_for_status()
        return resp.json()

    def get_history(self, address: str, limit: int = 10) -> Dict:
        """
        查询信用分历史变化

        Args:
            address: Agent 地址
            limit: 返回条数

        Returns:
            {
                "address": "0x...",
                "history": [
                    {"score": 850, "grade": "AAA", "calculated_at": 1715040000, ...},
                    ...
                ]
            }
        """
        resp = requests.get(
            f"{self.base_url}/api/v1/credit/{address}/history",
            params={"limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    def get_ranking(self, limit: int = 100) -> Dict:
        """
        查询信用分排行榜

        Args:
            limit: 返回数量

        Returns:
            {
                "ranking": [
                    {"rank": 1, "agent_id": "0x...", "total_score": 950, "grade": "AAA"},
                    ...
                ],
                "total": 100
            }
        """
        resp = requests.get(
            f"{self.base_url}/api/v1/credit/ranking",
            params={"limit": limit}
        )
        resp.raise_for_status()
        return resp.json()

    def refresh_score(
        self,
        address: str,
        records: list = None,
        credit_data: Dict = None,
        agent_info: Dict = None,
    ) -> Dict:
        """
        触发重新计算信用分

        Args:
            address: Agent 地址
            records: 履约记录列表
            credit_data: 信用货币数据
            agent_info: Agent 信息

        Returns:
            计算后的信用分结果
        """
        resp = requests.post(
            f"{self.base_url}/api/v1/credit/{address}/refresh",
            json={
                "agent_id": address,
                "wallet": address,
                "records": records or [],
                "credit_data": credit_data or {},
                "agent_info": agent_info or {},
            }
        )
        resp.raise_for_status()
        return resp.json()


# 维度名称映射
DIMENSION_NAMES = {
    "S": "Stability",
    "A": "Activity",
    "C": "Creditworthiness",
    "R": "Reliability",
    "E": "Ecosystem",
}


def format_score(result: Dict) -> str:
    """
    格式化信用分结果为可读字符串

    Args:
        result: get_score() 返回的结果

    Returns:
        格式化后的字符串
    """
    lines = [
        f"Agent: {result.get('agent_id', 'N/A')}",
        f"Score: {result.get('total_score', 0)} ({result.get('grade', 'C')})",
        f"Cold Start: {'Yes' if result.get('is_cold_start') else 'No'}",
        "",
        "Dimensions:",
    ]

    dims = result.get("dimensions", {})
    for code in ["S", "A", "C", "R", "E"]:
        dim = dims.get(code, {})
        name = dim.get("name", DIMENSION_NAMES.get(code, code))
        score = dim.get("score", 0)
        max_score = dim.get("max", 200)
        lines.append(f"  {code} - {name}: {score}/{max_score}")

    return "\n".join(lines)
