"""
信用分验证工具

任何人都可以使用此工具验证信用分的真实性
"""

import hashlib
import json
import time
from typing import Dict, List, Optional

from .calculator import SacredCalculator
from .models import PerformanceRecord, SacredScore


class CreditVerifier:
    """信用分验证器"""

    def __init__(self):
        self._calculator = SacredCalculator()

    def verify_score(
        self,
        agent_id: str,
        wallet: str,
        records: List[PerformanceRecord],
        claimed_score: SacredScore,
        credit_data: Dict = None,
        agent_info: Dict = None,
    ) -> Dict:
        """
        验证信用分是否正确

        Args:
            agent_id: Agent ID
            wallet: 钱包地址
            records: 履约记录列表
            claimed_score: 声称的信用分
            credit_data: 信用货币数据
            agent_info: Agent信息

        Returns:
            {
                "valid": True/False,
                "claimed_score": 850.5,
                "calculated_score": 850.5,
                "claimed_hash": "abc123...",
                "calculated_hash": "abc123...",
                "claimed_grade": "AAA",
                "calculated_grade": "AAA",
                "dimension_match": {
                    "S": True,
                    "A": True,
                    "C": True,
                    "R": True,
                    "E": True
                },
                "verified_at": 1234567890
            }
        """
        # 重新计算信用分
        calculated = self._calculator.calculate(
            agent_id=agent_id,
            wallet=wallet,
            records=records,
            credit_data=credit_data or {},
            agent_info=agent_info or {},
            now=claimed_score.calculated_at,  # 使用相同的时间戳
        )

        # 对比结果
        dimension_match = {}
        for dim_code in ["S", "A", "C", "R", "E"]:
            claimed_dim = claimed_score.dimensions[dim_code]
            calculated_dim = calculated.dimensions[dim_code]
            # 允许0.1的浮点误差
            dimension_match[dim_code] = abs(
                claimed_dim.weighted_score - calculated_dim.weighted_score
            ) < 0.1

        score_match = abs(claimed_score.total_score - calculated.total_score) < 0.1
        grade_match = claimed_score.grade == calculated.grade
        hash_match = claimed_score.snapshot_hash == calculated.snapshot_hash

        return {
            "valid": score_match and grade_match and hash_match and all(dimension_match.values()),
            "claimed_score": claimed_score.total_score,
            "calculated_score": calculated.total_score,
            "claimed_hash": claimed_score.snapshot_hash,
            "calculated_hash": calculated.snapshot_hash,
            "claimed_grade": claimed_score.grade,
            "calculated_grade": calculated.grade,
            "dimension_match": dimension_match,
            "all_dimensions_match": all(dimension_match.values()),
            "verified_at": int(time.time()),
        }

    def verify_from_api(
        self,
        api_base_url: str,
        agent_id: str,
        api_key: str = None,
    ) -> Dict:
        """
        从API获取数据并验证

        Args:
            api_base_url: API基础URL（如 http://localhost:3458）
            agent_id: Agent ID
            api_key: API密钥（可选）

        Returns:
            验证结果
        """
        import requests

        headers = {}
        if api_key:
            headers["X-CryptoMinds-API-Key"] = api_key

        # 1. 获取信用分
        score_resp = requests.get(
            f"{api_base_url}/api/v1/credit/{agent_id}",
            headers=headers,
        )
        score_resp.raise_for_status()
        score_data = score_resp.json()

        if score_data.get("ok") is False or score_data.get("error"):
            return {
                "valid": False,
                "error": score_data.get("error", "Failed to fetch credit score"),
            }

        claimed_score = SacredScore.from_dict(score_data)

        # 2. 获取履约记录
        records_resp = requests.get(
            f"{api_base_url}/api/v1/credit/{agent_id}/records",
            headers=headers,
        )
        records_resp.raise_for_status()
        records_data = records_resp.json()

        records = [PerformanceRecord.from_dict(r) for r in records_data.get("records", [])]

        # 3. 获取Agent信息（如果有）
        agent_info = score_data.get("agent_info", {})
        credit_data = score_data.get("credit_data", {})

        # 4. 验证
        return self.verify_score(
            agent_id=agent_id,
            wallet=claimed_score.wallet,
            records=records,
            claimed_score=claimed_score,
            credit_data=credit_data,
            agent_info=agent_info,
        )

    def generate_verification_report(self, verification_result: Dict) -> str:
        """生成人类可读的验证报告"""
        if not verification_result.get("valid"):
            return f"""
❌ 验证失败

声称的分数: {verification_result.get('claimed_score', 'N/A')}
计算的分数: {verification_result.get('calculated_score', 'N/A')}
声称的等级: {verification_result.get('claimed_grade', 'N/A')}
计算的等级: {verification_result.get('calculated_grade', 'N/A')}
声称的哈希: {verification_result.get('claimed_hash', 'N/A')}
计算的哈希: {verification_result.get('calculated_hash', 'N/A')}

维度匹配:
{self._format_dimension_match(verification_result.get('dimension_match', {}))}

错误: {verification_result.get('error', '分数不匹配')}
"""

        return f"""
✅ 验证成功

信用分: {verification_result['claimed_score']}
等级: {verification_result['claimed_grade']}
哈希: {verification_result['claimed_hash']}

所有维度匹配: {'是' if verification_result.get('all_dimensions_match') else '否'}
{self._format_dimension_match(verification_result.get('dimension_match', {}))}

验证时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(verification_result['verified_at']))}
"""

    def _format_dimension_match(self, dimension_match: Dict) -> str:
        """格式化维度匹配结果"""
        lines = []
        dim_names = {
            "S": "Stability (稳定性)",
            "A": "Activity (活跃度)",
            "C": "Creditworthiness (履约力)",
            "R": "Reliability (可信度)",
            "E": "Ecosystem (生态度)",
        }
        for dim_code, matched in dimension_match.items():
            status = "✓" if matched else "✗"
            lines.append(f"  {status} {dim_names.get(dim_code, dim_code)}")
        return "\n".join(lines)


def verify_credit_score_cli():
    """命令行验证工具"""
    import argparse

    parser = argparse.ArgumentParser(description="验证CryptoMinds信用分")
    parser.add_argument("--api", default="http://localhost:3458", help="API基础URL")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--api-key", help="API密钥（可选）")

    args = parser.parse_args()

    verifier = CreditVerifier()
    result = verifier.verify_from_api(
        api_base_url=args.api,
        agent_id=args.agent_id,
        api_key=args.api_key,
    )

    report = verifier.generate_verification_report(result)
    print(report)

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    import sys
    sys.exit(verify_credit_score_cli())
