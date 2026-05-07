"""
SACRED 五维信用分计算引擎

S - Stability 稳定性: 成功率 120 + 超时率 40 + 不活跃衰减 40 = 200
A - Activity 活跃度: 近期任务量 100 + 连续活跃 60 + 时段覆盖 40 = 200
C - Creditworthiness 履约力: 质押量 100 + 托管金额 50 + 信用货币接受度 50 = 200
R - Reliability 可信度: 争议赢率 70 + 验证门评分 70 + 严重违约惩罚 60 = 200
E - Ecosystem 生态度: 交互Agent数 80 + 信任网络 60 + 跨链活跃 60 = 200
"""

import math
import time
from typing import Dict

from .config import (
    DIMENSION_MAX, LONG_HALF_LIFE,
    SEVERE_VIOLATION_PENALTY,
)
from .models import SacredScore, DimensionScore
from .decay import time_decay, days_between, no_decay_violation
from .cold_start import ColdStartManager


def _status_value(status) -> str:
    """Normalize status enums from credit_score or reputation modules."""
    return getattr(status, "value", str(status))


class SacredCalculator:
    """SACRED 五维信用分计算器"""

    def __init__(self):
        self._cold_start = ColdStartManager()

    def calculate(
        self,
        agent_id: str,
        wallet: str,
        records: list = None,
        credit_data: Dict = None,
        agent_info: Dict = None,
        now: int = None,
    ) -> SacredScore:
        """
        计算完整 SACRED 分数

        Args:
            agent_id: Agent ID
            wallet: 钱包地址
            records: 履约记录列表 (PerformanceRecord)
            credit_data: 信用货币数据 {"currencies": [], "accepted_count": 0}
            agent_info: Agent 信息 {"staked": 0, "active_chains": [], "counterparts": 0}
            now: 当前时间戳（测试用）
        """
        if now is None:
            now = int(time.time())

        records = records or []
        credit_data = credit_data or {}
        agent_info = agent_info or {}

        score = SacredScore(agent_id=agent_id, wallet=wallet, calculated_at=now)

        # 逐维度计算
        score.stability = self._calc_stability(records, now)
        score.activity = self._calc_activity(records, now)
        score.creditworthiness = self._calc_creditworthiness(records, credit_data, agent_info)
        score.reliability = self._calc_reliability(records, now)
        score.ecosystem = self._calc_ecosystem(records, credit_data, agent_info)

        # 汇总
        score.compute_total()

        # 冷启动调整
        task_count = len(records)
        score = self._cold_start.apply_cold_start(score, task_count)

        # 哈希
        score.compute_hash()

        return score

    # ── S 维：稳定性 ─────────────────────────────────

    def _calc_stability(self, records: list, now: int) -> DimensionScore:
        """稳定性 0-200

        - 成功率贡献 100 分: decay-weighted success_rate * 100
        - 超时率扣分 60 分: (1 - timeout_rate) * 60
        - 不活跃衰减 40 分: active_ratio * 40
        """
        components = {}

        if not records:
            return DimensionScore("S", "Stability", 0, 0, components)

        total = len(records)

        # 1. 衰减加权成功率 -> 120 分
        weighted_success = 0.0
        weighted_total = 0.0
        for r in records:
            d = days_between(r.created_at, now)
            w = time_decay(d, LONG_HALF_LIFE)
            weighted_total += w
            if _status_value(r.status) == "settled":
                weighted_success += w

        success_rate = weighted_success / weighted_total if weighted_total > 0 else 0.0
        success_score = success_rate * 120
        components["success_rate"] = round(success_score, 1)

        # 2. 超时率 -> 40 分
        timeout_count = len([r for r in records if _status_value(r.status) == "timeout"])
        timeout_rate = timeout_count / total if total > 0 else 0.0
        timeout_score = (1 - timeout_rate) * 40
        components["timeout_rate"] = round(timeout_score, 1)

        # 3. 不活跃衰减 -> 40 分
        latest_ts = max(r.created_at for r in records) if records else 0
        days_since_last = days_between(latest_ts, now)
        active_ratio = max(0.0, 1.0 - days_since_last / 90.0)
        activity_score = active_ratio * 40  # S维总分: 120+40+40=200
        components["inactivity_decay"] = round(activity_score, 1)

        raw = success_score + timeout_score + activity_score
        weighted = min(DIMENSION_MAX, max(0.0, raw))

        return DimensionScore("S", "Stability", round(raw, 1), round(weighted, 1), components)

    # ── A 维：活跃度 ─────────────────────────────────

    def _calc_activity(self, records: list, now: int) -> DimensionScore:
        """活跃度 0-200

        - 近期任务量 80 分
        - 连续活跃天数 70 分
        - 时段覆盖 50 分
        """
        components = {}

        if not records:
            return DimensionScore("A", "Activity", 0, 0, components)

        # 1. 近期任务量 -> 100 分（7天内每1个任务得10分，最多100）
        week_ago = now - 7 * 86400
        recent_records = [r for r in records if r.created_at >= week_ago]
        recent_score = min(100, len(recent_records) * 10)
        components["recent_tasks"] = round(recent_score, 1)

        # 2. 连续活跃天数 -> 60 分（30天满分）
        # 基于有记录的日期数
        record_days = set()
        for r in records:
            record_days.add(r.created_at // 86400)

        # 找从今天往回的连续活跃天数
        today = now // 86400
        consecutive = 0
        for i in range(30):
            if (today - i) in record_days:
                consecutive += 1
            else:
                break

        consecutive_score = min(60, consecutive / 30 * 60)
        components["consecutive_days"] = round(consecutive_score, 1)

        # 3. 时段覆盖 -> 40 分（24h 中有多少小时有活动）
        active_hours = set()
        for r in records:
            # 用 created_at 的小时数（UTC）
            hour = (r.created_at % 86400) // 3600
            active_hours.add(hour)

        hour_coverage = len(active_hours) / 24.0
        coverage_score = hour_coverage * 40
        components["hour_coverage"] = round(coverage_score, 1)

        raw = recent_score + consecutive_score + coverage_score
        weighted = min(DIMENSION_MAX, max(0.0, raw))

        return DimensionScore("A", "Activity", round(raw, 1), round(weighted, 1), components)

    # ── C 维：履约力 ─────────────────────────────────

    def _calc_creditworthiness(self, records: list, credit_data: Dict,
                               agent_info: Dict) -> DimensionScore:
        """履约力 0-200

        - 质押量 80 分
        - 托管金额 60 分
        - 信用货币接受度 60 分
        """
        components = {}

        # 1. 质押量 -> 100 分（5 BNB 满分）
        staked = float(agent_info.get("staked", 0))
        staked_score = min(100, math.log10(max(1, staked + 1)) * 45)
        components["staked"] = round(staked_score, 1)

        # 2. 托管金额 -> 50 分（历史总托管量）
        total_escrow = sum(
            float(r.payment_amount) for r in records
            if _status_value(r.status) == "settled" and r.payment_amount
        )
        escrow_score = min(50, math.log10(max(1, total_escrow + 1)) * 18)
        components["escrow_volume"] = round(escrow_score, 1)

        # 3. 信用货币接受度 -> 50 分（发行的货币被10个Agent接受满分）
        accepted_count = credit_data.get("accepted_count", 0)
        acceptance_score = min(50, accepted_count / 10 * 50)
        components["currency_acceptance"] = round(acceptance_score, 1)

        raw = staked_score + escrow_score + acceptance_score
        weighted = min(DIMENSION_MAX, max(0.0, raw))

        return DimensionScore("C", "Creditworthiness", round(raw, 1),
                              round(weighted, 1), components)

    # ── R 维：可信度 ─────────────────────────────────

    def _calc_reliability(self, records: list, now: int) -> DimensionScore:
        """可信度 0-200

        - 争议赢率 70 分: 争议中赢的比例 * 70
        - 验证门评分 70 分: avg_verification_score * 70
        - 严重违约惩罚 60 分: 60 - 严重违约次数 * 50
        """
        components = {}

        if not records:
            return DimensionScore("R", "Reliability", 0, 0, components)

        # 1. 争议赢率 -> 70 分
        disputed_records = [r for r in records if r.disputed]
        if disputed_records:
            seller_won = len([r for r in disputed_records if r.resolution != "buyer_win"])
            dispute_win_rate = seller_won / len(disputed_records)
        else:
            dispute_win_rate = 1.0  # 没有争议，满分

        dispute_score = dispute_win_rate * 70
        components["dispute_win_rate"] = round(dispute_score, 1)

        # 2. 验证门评分 -> 70 分
        scores = [r.score for r in records if r.success and r.score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0.5
        verification_score = avg_score * 70
        components["verification_score"] = round(verification_score, 1)

        # 3. 严重违约惩罚 -> 60 分
        severe_count = 0
        for r in records:
            if r.disputed and no_decay_violation(r.resolution):
                severe_count += 1
            elif _status_value(r.status) == "timeout":
                severe_count += 1

        penalty = min(60, severe_count * SEVERE_VIOLATION_PENALTY)
        violation_score = max(0, 60 - penalty)
        components["severe_violations"] = round(violation_score, 1)

        raw = dispute_score + verification_score + violation_score
        weighted = min(DIMENSION_MAX, max(0.0, raw))

        return DimensionScore("R", "Reliability", round(raw, 1), round(weighted, 1), components)

    # ── E 维：生态度 ─────────────────────────────────

    def _calc_ecosystem(self, records: list, credit_data: Dict, agent_info: Dict) -> DimensionScore:
        """生态度 0-200

        - 交互Agent数 80 分: unique_counterparts / 50 * 80
        - 信任网络 60 分: accepted_currencies_ratio * 60
        - 跨链活跃 60 分: chain_count / 3 * 60
        """
        components = {}

        # 1. 交互 Agent 数 -> 80 分（20个不同对手方满分）
        counterparts = int(agent_info.get("counterparts", 0))
        counterpart_score = min(80, counterparts / 20 * 80)
        components["counterparts"] = round(counterpart_score, 1)

        # 2. 信任网络 -> 60 分（接受的信用货币占总数的比例）
        currencies = credit_data.get("currencies", [])
        total_currencies = max(1, len(currencies)) if currencies else 1
        accepted_by_agent = credit_data.get("accepted_by_agent", 0)
        trust_score = min(60, accepted_by_agent / total_currencies * 60)
        components["trust_network"] = round(trust_score, 1)

        # 3. 跨链活跃 -> 60 分（3条链满分）
        active_chains = agent_info.get("active_chains", [])
        chain_count = len(active_chains) if active_chains else 0
        if chain_count == 0 and records:
            # 从记录推断
            chains = set(r.chain for r in records if r.chain)
            chain_count = len(chains)
        chain_score = min(60, chain_count / 3 * 60)
        components["cross_chain"] = round(chain_score, 1)

        raw = counterpart_score + trust_score + chain_score
        weighted = min(DIMENSION_MAX, max(0.0, raw))

        return DimensionScore("E", "Ecosystem", round(raw, 1), round(weighted, 1), components)
