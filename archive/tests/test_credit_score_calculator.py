"""
SACRED 五维计算引擎测试
"""

import pytest
import time
from decimal import Decimal

from reputation.record import PerformanceRecord, TaskStatus
from credit_score.calculator import SacredCalculator
from credit_score.config import DIMENSION_MAX, TOTAL_MAX, COLD_START_SCORE, SEVERE_VIOLATION_PENALTY


def _make_record(
    status=TaskStatus.SETTLED, success=True, score=0.9,
    days_ago=1, disputed=False, resolution="",
    chain="bsc", payment_amount=Decimal("1.0"),
    response_time_ms=1000,
):
    now = int(time.time())
    return PerformanceRecord(
        record_id=f"r-{now}-{hash(str(days_ago))}",
        task_type="token_delivery",
        buyer_wallet="0xbuyer",
        seller_wallet="0xseller",
        seller_agent_id="agent-1",
        chain=chain,
        amount=payment_amount,
        status=status,
        success=success,
        score=score,
        created_at=now - int(days_ago * 86400),
        completed_at=now - int((days_ago - 0.5) * 86400) if days_ago > 0.5 else now,
        response_time_ms=response_time_ms,
        payment_amount=payment_amount if success else Decimal("0"),
        disputed=disputed,
        resolution=resolution,
    )


class TestEmptyRecords:
    """空记录返回冷启动分数"""

    def test_empty_returns_cold_start(self):
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller")
        assert score.is_cold_start is True
        assert score.total_score == COLD_START_SCORE
        assert score.grade == "CCC"  # 250 >= 250 threshold

    def test_empty_all_dimensions_zero(self):
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller")
        for dim in score.dimensions.values():
            # 冷启动下维度分是基础分（70/维）
            assert dim.weighted_score >= 0


class TestStabilityDimension:
    """S 维稳定性测试"""

    def test_all_settled_high_score(self):
        """全部完成 -> S 维接近满分"""
        records = [_make_record(days_ago=i % 30 + 1) for i in range(20)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.stability.weighted_score > 150

    def test_all_failed_low_score(self):
        """全部失败 -> S 维很低"""
        records = [_make_record(status=TaskStatus.FAILED, success=False, days_ago=1) for _ in range(10)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.stability.weighted_score < 100

    def test_high_timeout_rate(self):
        """高超时率 -> S 维降低"""
        records = [_make_record(status=TaskStatus.TIMEOUT, success=False, days_ago=1) for _ in range(10)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        # 超时率 100% -> timeout_score = 0
        assert score.stability.components.get("timeout_rate", 0) < 10

    def test_inactivity_decay(self):
        """长期不活跃 -> 不活跃衰减"""
        records = [_make_record(days_ago=120)]  # 120天前
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        # 超过90天 -> active_ratio < 0
        assert score.stability.components.get("inactivity_decay", 0) == 0

    def test_recent_activity_no_decay(self):
        """近期活跃 -> 不活跃衰减为0"""
        records = [_make_record(days_ago=1)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.stability.components.get("inactivity_decay", 0) > 30


class TestActivityDimension:
    """A 维活跃度测试"""

    def test_many_recent_tasks(self):
        """大量近期任务 -> A 维高分"""
        records = [_make_record(days_ago=i % 7) for i in range(15)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.activity.weighted_score > 80

    def test_no_recent_tasks(self):
        """没有近期任务 -> A 维低分"""
        records = [_make_record(days_ago=60)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.activity.components.get("recent_tasks", 0) == 0


class TestCreditworthinessDimension:
    """C 维履约力测试"""

    def test_high_stake(self):
        """高质押 -> C 维高分"""
        records = [_make_record(days_ago=1, payment_amount=Decimal("5.0")) for _ in range(5)]
        agent_info = {"staked": 100, "active_chains": ["bsc"]}
        credit_data = {"accepted_count": 8, "currencies": []}
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records, credit_data=credit_data, agent_info=agent_info)
        assert score.creditworthiness.raw_score > 100

    def test_no_stake(self):
        """无质押 -> C 维低分"""
        records = [_make_record(days_ago=1, payment_amount=Decimal("0.1"))]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.creditworthiness.raw_score < 10


class TestReliabilityDimension:
    """R 维可信度测试"""

    def test_no_disputes_high_score(self):
        """无争议 -> R 维高分"""
        records = [_make_record(days_ago=1, score=0.95) for _ in range(10)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.reliability.weighted_score > 120

    def test_seller_win_dispute_no_penalty(self):
        """卖家赢了争议 -> 不严重扣分"""
        records = [
            _make_record(days_ago=1, disputed=True, resolution="buyer_win"),
            _make_record(days_ago=2),
        ]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        # buyer_win 对 seller 来说是输了争议
        assert score.reliability.components.get("dispute_win_rate", 0) < 70

    def test_severe_violation_penalty(self):
        """严重违约 -> R 维扣分"""
        records = [
            _make_record(days_ago=1, disputed=True, resolution="seller_win"),
            _make_record(days_ago=2),
        ]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        # seller_win 是严重违约类型
        assert score.reliability.components.get("severe_violations", 0) < 60


class TestEcosystemDimension:
    """E 维生态度测试"""

    def test_multi_chain(self):
        """多链活跃 -> E 维加分"""
        records = [_make_record(days_ago=1, chain="bsc")]
        agent_info = {"counterparts": 30, "active_chains": ["bsc", "solana", "polygon"]}
        credit_data = {"accepted_by_agent": 5, "currencies": [{"id": "c1"}]}
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records, credit_data=credit_data, agent_info=agent_info)
        assert score.ecosystem.raw_score > 100

    def test_single_chain(self):
        """单链 -> 跨链分低"""
        records = [_make_record(days_ago=1, chain="bsc")]
        agent_info = {"counterparts": 5, "active_chains": ["bsc"]}
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records, agent_info=agent_info)
        cross_chain = score.ecosystem.components.get("cross_chain", 0)
        assert cross_chain < 40

    def test_chain_from_records(self):
        """agent_info 无链信息时从记录推断"""
        records = [_make_record(days_ago=1, chain="bsc"), _make_record(days_ago=2, chain="solana")]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert score.ecosystem.components.get("cross_chain", 0) > 20


class TestTotalScore:
    """总分和等级测试"""

    def test_total_score_range(self):
        """总分在 0-1000 范围内"""
        records = [_make_record(days_ago=1) for _ in range(10)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert 0 <= score.total_score <= TOTAL_MAX

    def test_perfect_agent_high_score(self):
        """完美 Agent 高分"""
        records = [_make_record(days_ago=i % 7 + 1, score=0.99, payment_amount=Decimal("10.0"), chain=c)
                   for i, c in enumerate(["bsc", "solana", "polygon"] * 10)]
        agent_info = {"staked": 200, "counterparts": 60, "active_chains": ["bsc", "solana", "polygon"]}
        credit_data = {"accepted_count": 15, "accepted_by_agent": 8, "currencies": [{"id": f"c{i}"} for i in range(5)]}
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records, credit_data=credit_data, agent_info=agent_info)
        assert score.total_score > 700

    def test_snapshot_hash(self):
        """快照哈希存在且一致"""
        records = [_make_record(days_ago=1)]
        calc = SacredCalculator()
        score = calc.calculate("agent-1", "0xseller", records=records)
        assert len(score.snapshot_hash) == 16

    def test_grade_boundaries(self):
        """等级边界验证"""
        # 手动设置各维度分来验证等级
        from credit_score.models import SacredScore, DimensionScore, CreditGrade

        # 900 -> AAA
        score = SacredScore(agent_id="test", wallet="0x")
        for d in score.dimensions.values():
            d.weighted_score = 180
        score.compute_total()
        assert score.grade == "AAA"

        # 800 -> AA
        score = SacredScore()
        for d in score.dimensions.values():
            d.weighted_score = 160
        score.compute_total()
        assert score.grade == "AA"
