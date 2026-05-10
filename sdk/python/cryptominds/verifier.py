"""
信用分验证工具
"""

from typing import Dict, Optional
from .client import CryptoMindsClient


def verify_credit_score(
    agent_id: str,
    api_url: str = "http://localhost:3458",
    api_key: Optional[str] = None,
) -> Dict:
    """
    验证信用分

    从API获取数据，重新计算信用分，对比哈希值

    Args:
        agent_id: Agent ID
        api_url: API基础URL
        api_key: API密钥（可选）

    Returns:
        {
            "valid": True/False,
            "claimed_score": 850.5,
            "calculated_score": 850.5,
            "claimed_hash": "abc123...",
            "calculated_hash": "abc123...",
            "message": "验证成功"
        }

    Example:
        >>> result = verify_credit_score("agent_001")
        >>> print(result["valid"])
        True
    """
    try:
        from credit.calculator import SacredCalculator
        from credit.models import PerformanceRecord, SacredScore
    except ImportError:
        return {
            "valid": False,
            "error": "缺少信用分算法模块。请在仓库根目录运行，或设置 PYTHONPATH=src 后重试。",
        }

    client = CryptoMindsClient(api_url=api_url, api_key=api_key)

    # 获取验证数据
    try:
        data = client.get_verification_data(agent_id)
    except Exception as e:
        return {
            "valid": False,
            "error": f"获取验证数据失败: {str(e)}",
        }

    if not data.get("ok"):
        return {
            "valid": False,
            "error": data.get("error", "获取验证数据失败"),
        }

    # 解析数据
    claimed_score = SacredScore.from_dict(data["score"])
    records = [PerformanceRecord.from_dict(r) for r in data.get("records", [])]
    agent_info = data.get("agent_info", {})
    credit_data = data.get("credit_data", {})

    # 重新计算
    calculator = SacredCalculator()
    calculated = calculator.calculate(
        agent_id=agent_id,
        wallet=claimed_score.wallet,
        records=records,
        credit_data=credit_data,
        agent_info=agent_info,
        now=claimed_score.calculated_at,
    )

    # 对比
    score_match = abs(claimed_score.total_score - calculated.total_score) < 0.1
    grade_match = claimed_score.grade == calculated.grade
    hash_match = claimed_score.snapshot_hash == calculated.snapshot_hash

    valid = score_match and grade_match and hash_match

    return {
        "valid": valid,
        "claimed_score": claimed_score.total_score,
        "calculated_score": calculated.total_score,
        "claimed_grade": claimed_score.grade,
        "calculated_grade": calculated.grade,
        "claimed_hash": claimed_score.snapshot_hash,
        "calculated_hash": calculated.snapshot_hash,
        "score_match": score_match,
        "grade_match": grade_match,
        "hash_match": hash_match,
        "message": "✅ 验证成功" if valid else "❌ 验证失败",
    }
