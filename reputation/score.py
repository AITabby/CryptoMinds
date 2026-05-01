"""
信誉分计算

基于履约记录计算 Agent 的信誉分。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
import time

from .record import PerformanceRecord, TaskStatus, RecordStore


@dataclass
class ReputationScore:
    """
    信誉分

    综合评估 Agent 的可靠性。
    """

    agent_id: str = ""
    wallet: str = ""

    # 基础指标
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    disputed_tasks: int = 0

    # 成功率
    success_rate: float = 0.0
    dispute_rate: float = 0.0

    # 交易量
    total_volume: Decimal = Decimal("0")
    avg_task_value: Decimal = Decimal("0")

    # 质量
    avg_score: float = 0.0          # 平均验证门评分
    avg_response_time_ms: int = 0

    # 时间衰减
    last_24h_tasks: int = 0
    last_24h_success_rate: float = 0.0
    last_7d_tasks: int = 0
    last_7d_success_rate: float = 0.0

    # 综合评分
    score: float = 0.0              # 0-5
    rank: str = ""                  # S, A, B, C, D

    # 计算时间
    calculated_at: int = 0

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "wallet": self.wallet,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "disputed_tasks": self.disputed_tasks,
            "success_rate": self.success_rate,
            "dispute_rate": self.dispute_rate,
            "total_volume": str(self.total_volume),
            "avg_task_value": str(self.avg_task_value),
            "avg_score": self.avg_score,
            "avg_response_time_ms": self.avg_response_time_ms,
            "last_24h_tasks": self.last_24h_tasks,
            "last_24h_success_rate": self.last_24h_success_rate,
            "last_7d_tasks": self.last_7d_tasks,
            "last_7d_success_rate": self.last_7d_success_rate,
            "score": self.score,
            "rank": self.rank,
            "calculated_at": self.calculated_at,
        }


class ReputationCalculator:
    """
    信誉分计算器

    计算逻辑：
    1. 基础分：成功率 × 3
    2. 质量加成：平均评分 × 1
    3. 交易量加成：log(volume) × 0.1
    4. 响应速度加成：快速响应加分
    5. 时间衰减：近期表现权重更高
    """

    # 权重配置
    WEIGHTS = {
        "success_rate": 0.4,        # 成功率权重
        "quality": 0.3,             # 质量权重
        "volume": 0.15,             # 交易量权重
        "response_time": 0.15,      # 响应时间权重
    }

    # 响应时间阈值（毫秒）
    RESPONSE_TIME_THRESHOLDS = {
        "excellent": 1000,          # < 1秒
        "good": 5000,               # < 5秒
        "acceptable": 30000,        # < 30秒
    }

    def __init__(self, record_store: RecordStore = None):
        self.record_store = record_store or RecordStore()

    def calculate(
        self,
        agent_id: str,
        wallet: str,
        records: List[PerformanceRecord] = None
    ) -> ReputationScore:
        """
        计算信誉分

        Args:
            agent_id: Agent ID
            wallet: 钱包地址
            records: 履约记录（可选，不传则从存储获取）

        Returns:
            ReputationScore
        """
        # 获取记录
        if records is None:
            records = self.record_store.get_by_seller(wallet, limit=10000)

        if not records:
            return ReputationScore(
                agent_id=agent_id,
                wallet=wallet,
                score=0.0,
                rank="D",
                calculated_at=int(time.time()),
            )

        # 计算基础指标
        total = len(records)
        completed = len([r for r in records if r.status == TaskStatus.SETTLED])
        failed = len([r for r in records if r.status in (TaskStatus.FAILED, TaskStatus.SETTLEMENT_FAILED)])
        disputed = len([r for r in records if r.disputed])

        success_rate = completed / total if total > 0 else 0
        dispute_rate = disputed / total if total > 0 else 0

        # 交易量
        total_volume = sum(r.payment_amount for r in records if r.success)
        avg_task_value = total_volume / completed if completed > 0 else Decimal("0")

        # 质量
        scores = [r.score for r in records if r.success and r.score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0

        response_times = [r.response_time_ms for r in records if r.response_time_ms > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # 时间衰减
        now = int(time.time())
        day_ago = now - 86400
        week_ago = now - 604800

        last_24h_records = [r for r in records if r.created_at >= day_ago]
        last_24h_tasks = len(last_24h_records)
        last_24h_completed = len([r for r in last_24h_records if r.status == TaskStatus.SETTLED])
        last_24h_success_rate = last_24h_completed / last_24h_tasks if last_24h_tasks > 0 else 0

        last_7d_records = [r for r in records if r.created_at >= week_ago]
        last_7d_tasks = len(last_7d_records)
        last_7d_completed = len([r for r in last_7d_records if r.status == TaskStatus.SETTLED])
        last_7d_success_rate = last_7d_completed / last_7d_tasks if last_7d_tasks > 0 else 0

        # 计算综合评分
        score = self._calculate_score(
            success_rate=success_rate,
            avg_score=avg_score,
            total_volume=total_volume,
            avg_response_time=avg_response_time,
            last_24h_success_rate=last_24h_success_rate,
        )

        # 确定等级
        rank = self._get_rank(score)

        return ReputationScore(
            agent_id=agent_id,
            wallet=wallet,
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            disputed_tasks=disputed,
            success_rate=success_rate,
            dispute_rate=dispute_rate,
            total_volume=total_volume,
            avg_task_value=avg_task_value,
            avg_score=avg_score,
            avg_response_time_ms=int(avg_response_time),
            last_24h_tasks=last_24h_tasks,
            last_24h_success_rate=last_24h_success_rate,
            last_7d_tasks=last_7d_tasks,
            last_7d_success_rate=last_7d_success_rate,
            score=score,
            rank=rank,
            calculated_at=int(time.time()),
        )

    def _calculate_score(
        self,
        success_rate: float,
        avg_score: float,
        total_volume: Decimal,
        avg_response_time: float,
        last_24h_success_rate: float,
    ) -> float:
        """计算综合评分"""

        import math
        volume_float = float(total_volume)

        # 1. 成功率分 (0-3)
        # 成功率 95% = 2.85 分，100% = 3 分
        success_score = success_rate * 3

        # 2. 质量分 (0-1)
        # 平均验证门评分 0.95 = 0.95 分
        quality_score = avg_score

        # 3. 交易量分 (0-0.5)
        # log10(47.5) ≈ 1.67, 给 0.3 分左右
        volume_score = min(0.5, math.log10(max(1, volume_float + 1)) * 0.15)

        # 4. 响应时间分 (0-0.5)
        response_score = self._get_response_score(avg_response_time) * 0.5

        # 5. 近期表现加成
        recent_bonus = 0
        if last_24h_success_rate >= 0.98:
            recent_bonus = 0.3
        elif last_24h_success_rate >= 0.95:
            recent_bonus = 0.2
        elif last_24h_success_rate >= 0.90:
            recent_bonus = 0.1

        # 总分
        total = success_score + quality_score + volume_score + response_score + recent_bonus

        # 限制在 0-5
        return min(5.0, max(0.0, total))

    def _get_response_score(self, avg_response_time: float) -> float:
        """响应时间评分"""
        if avg_response_time <= 0:
            return 0.5  # 无数据，给中等分

        if avg_response_time < self.RESPONSE_TIME_THRESHOLDS["excellent"]:
            return 1.0
        elif avg_response_time < self.RESPONSE_TIME_THRESHOLDS["good"]:
            return 0.8
        elif avg_response_time < self.RESPONSE_TIME_THRESHOLDS["acceptable"]:
            return 0.5
        else:
            return 0.2

    def _get_rank(self, score: float) -> str:
        """确定等级"""
        if score >= 4.5:
            return "S"
        elif score >= 4.0:
            return "A"
        elif score >= 3.5:
            return "B"
        elif score >= 3.0:
            return "C"
        else:
            return "D"
