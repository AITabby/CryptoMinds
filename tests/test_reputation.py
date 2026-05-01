"""Tests for ReputationCalculator — scoring, ranks, response thresholds."""
from decimal import Decimal
import time
import pytest

from reputation.score import ReputationCalculator, ReputationScore
from reputation.record import PerformanceRecord, TaskStatus, RecordStore


def _make_record(status=TaskStatus.SETTLED, score=0.9, amount=Decimal("1.0"),
                 response_ms=500, wallet="0xseller", disputed=False,
                 created_at=None):
    if created_at is None:
        created_at = int(time.time())
    return PerformanceRecord.create(
        task_id=f"task-{int(time.time())}",
        task_type="token_delivery",
        buyer_wallet="0xbuyer",
        seller_wallet=wallet,
        seller_agent_id="agent-1",
        chain="bsc",
        amount=amount,
        status=status,
        success=(status == TaskStatus.SETTLED),
        score=score,
        response_time_ms=response_ms,
        payment_amount=amount if status == TaskStatus.SETTLED else Decimal("0"),
        evidence={},
    )


class TestCalculateEmpty:

    def test_no_records_returns_zero(self):
        store = RecordStore()
        calc = ReputationCalculator(store)
        result = calc.calculate("agent-1", "0xseller")
        assert result.score == 0.0
        assert result.rank == "D"
        assert result.total_tasks == 0


class TestCalculateWithRecords:

    def test_all_settled_gives_high_score(self):
        records = [_make_record(status=TaskStatus.SETTLED, score=1.0, response_ms=500)
                   for _ in range(5)]
        calc = ReputationCalculator()
        result = calc.calculate("agent-1", "0xseller", records=records)
        assert result.success_rate == 1.0
        assert result.completed_tasks == 5
        assert result.score >= 3.0

    def test_all_failed_gives_low_score(self):
        records = [_make_record(status=TaskStatus.FAILED, score=0.0, response_ms=0)
                   for _ in range(5)]
        calc = ReputationCalculator()
        result = calc.calculate("agent-1", "0xseller", records=records)
        assert result.success_rate == 0.0
        assert result.failed_tasks == 5
        assert result.score < 3.0

    def test_mixed_statuses(self):
        records = [
            _make_record(status=TaskStatus.SETTLED, score=0.9),
            _make_record(status=TaskStatus.FAILED, score=0.0),
        ]
        calc = ReputationCalculator()
        result = calc.calculate("agent-1", "0xseller", records=records)
        assert result.total_tasks == 2
        assert result.completed_tasks == 1
        assert result.failed_tasks == 1
        assert result.success_rate == 0.5


class TestResponseScore:

    def test_excellent_response(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(500) == 1.0

    def test_good_response(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(3000) == 0.8

    def test_acceptable_response(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(15000) == 0.5

    def test_slow_response(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(60000) == 0.2

    def test_zero_response_returns_mid(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(0) == 0.5

    def test_negative_response_returns_mid(self):
        calc = ReputationCalculator()
        assert calc._get_response_score(-1) == 0.5


class TestRank:

    def test_rank_S(self):
        calc = ReputationCalculator()
        assert calc._get_rank(4.8) == "S"

    def test_rank_A(self):
        calc = ReputationCalculator()
        assert calc._get_rank(4.2) == "A"

    def test_rank_B(self):
        calc = ReputationCalculator()
        assert calc._get_rank(3.7) == "B"

    def test_rank_C(self):
        calc = ReputationCalculator()
        assert calc._get_rank(3.2) == "C"

    def test_rank_D(self):
        calc = ReputationCalculator()
        assert calc._get_rank(2.5) == "D"

    def test_boundary_S_A(self):
        calc = ReputationCalculator()
        assert calc._get_rank(4.5) == "S"
        assert calc._get_rank(4.49) == "A"


class TestRecentBonus:

    def test_98_percent_bonus(self):
        calc = ReputationCalculator()
        score = calc._calculate_score(1.0, 0.5, Decimal("10"), 500, 0.98)
        # base=3 + quality=0.5 + volume(~0.15) + response(0.5) + recent(0.3)
        assert score >= 3.5

    def test_95_percent_bonus(self):
        score = ReputationCalculator()._calculate_score(1.0, 0.5, Decimal("10"), 500, 0.95)
        assert score >= 3.4

    def test_90_percent_bonus(self):
        score = ReputationCalculator()._calculate_score(1.0, 0.5, Decimal("10"), 500, 0.90)
        assert score >= 3.3

    def test_no_recent_bonus(self):
        score = ReputationCalculator()._calculate_score(1.0, 0.5, Decimal("10"), 500, 0.80)
        # No recent bonus should be lower
        base = 3.0 + 0.5 + 0.15 + 0.5  # ~4.15
        assert score < base + 0.1


class TestScoreCapped:

    def test_max_score_5(self):
        score = ReputationCalculator()._calculate_score(1.0, 1.0, Decimal("10000"), 100, 1.0)
        assert score <= 5.0

    def test_min_score_0(self):
        score = ReputationCalculator()._calculate_score(0.0, 0.0, Decimal("0"), 60000, 0.0)
        assert score >= 0.0