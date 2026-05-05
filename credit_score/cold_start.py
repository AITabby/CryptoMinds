"""
新 Agent 冷启动逻辑
"""

from .config import COLD_START_SCORE, COLD_START_THRESHOLD, COLD_START_MAX_BOOST
from .models import SacredScore


class ColdStartManager:
    """新 Agent 冷启动管理"""

    def is_cold_start(self, task_count: int) -> bool:
        """判断是否处于冷启动期"""
        return task_count < COLD_START_THRESHOLD

    def apply_cold_start(self, score: SacredScore, task_count: int) -> SacredScore:
        """应用冷启动调整

        线性插值: 前 N 个任务区间内，分数从基础分过渡到真实分
        """
        if not self.is_cold_start(task_count):
            score.is_cold_start = False
            return score

        score.is_cold_start = True

        # 线性过渡比例
        real_ratio = self._progress_ratio(task_count)

        # 各维度和总分从冷启动基础分过渡到真实分
        base_per_dim = COLD_START_SCORE / 5.0  # 每个维度 70 分

        for dim in score.dimensions.values():
            dim.weighted_score = base_per_dim * (1 - real_ratio) + dim.weighted_score * real_ratio

        score.compute_total()

        # 快速通道加成（随真实比例增长，最多 MAX_BOOST）
        boost = real_ratio * COLD_START_MAX_BOOST
        score.total_score = min(1000.0, score.total_score + boost)
        score.grade = self._grade_from_score(score.total_score)

        return score

    def get_boost(self, task_count: int) -> float:
        """获取当前快速通道加成"""
        return self._progress_ratio(task_count) * COLD_START_MAX_BOOST

    def _progress_ratio(self, task_count: int) -> float:
        if COLD_START_THRESHOLD <= 1:
            return 1.0
        return min(1.0, max(0.0, task_count / (COLD_START_THRESHOLD - 1)))

    def _grade_from_score(self, score: float) -> str:
        from .models import CreditGrade
        return CreditGrade.from_score(score).value
