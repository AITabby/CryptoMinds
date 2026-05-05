"""
时间衰减测试
"""

import math
import pytest
import time

from credit_score.decay import time_decay, days_between, no_decay_violation, apply_decay_to_records
from credit_score.config import SHORT_HALF_LIFE, LONG_HALF_LIFE, SEVERE_VIOLATION_TYPES


class TestTimeDecay:
    def test_zero_days(self):
        """当天不衰减"""
        assert time_decay(0, 30) == 1.0

    def test_negative_days(self):
        """负数天数不衰减"""
        assert time_decay(-1, 30) == 1.0

    def test_one_half_life(self):
        """一个半衰期后权重约0.5"""
        result = time_decay(30, 30)
        assert abs(result - 0.5) < 0.01

    def test_two_half_lives(self):
        """两个半衰期后权重约0.25"""
        result = time_decay(60, 30)
        assert abs(result - 0.25) < 0.02

    def test_three_half_lives(self):
        """三个半衰期后权重约0.125"""
        result = time_decay(90, 30)
        assert abs(result - 0.125) < 0.02

    def test_long_half_life_slower_decay(self):
        """长半衰期衰减更慢"""
        short = time_decay(30, SHORT_HALF_LIFE)
        long = time_decay(30, LONG_HALF_LIFE)
        assert long > short

    def test_decay_decreases_with_time(self):
        """越久衰减越多"""
        d1 = time_decay(10, 30)
        d10 = time_decay(100, 30)
        d100 = time_decay(1000, 30)
        assert d1 > d10 > d100


class TestDaysBetween:
    def test_same_time(self):
        assert days_between(1000, 1000) == 0.0

    def test_one_day(self):
        assert days_between(0, 86400) == 1.0

    def test_negative_returns_zero(self):
        assert days_between(86400, 0) == 0.0

    def test_half_day(self):
        assert days_between(0, 43200) == 0.5


class TestNoDecayViolation:
    def test_seller_win(self):
        assert no_decay_violation("seller_win") is True

    def test_timeout(self):
        assert no_decay_violation("timeout") is True

    def test_buyer_win(self):
        assert no_decay_violation("buyer_win") is False

    def test_split(self):
        assert no_decay_violation("split") is False

    def test_empty(self):
        assert no_decay_violation("") is False


class TestApplyDecayToRecords:
    def test_empty_records(self):
        result = apply_decay_to_records([], SHORT_HALF_LIFE)
        assert result == []

    def test_single_record(self):
        """单条记录权重计算"""
        from reputation.record import PerformanceRecord, TaskStatus
        now = int(time.time())
        record = PerformanceRecord(
            record_id="r1", status=TaskStatus.SETTLED,
            created_at=now - 86400,  # 1天前
        )
        result = apply_decay_to_records([record], SHORT_HALF_LIFE, now)
        assert len(result) == 1
        _, weight = result[0]
        # 1天前的衰减: exp(-1/30) ≈ 0.967
        assert abs(weight - math.exp(-1/30)) < 0.01

    def test_multiple_records_different_ages(self):
        """多条不同年龄的记录，新的权重更高"""
        from reputation.record import PerformanceRecord, TaskStatus
        now = int(time.time())
        old = PerformanceRecord(record_id="r1", status=TaskStatus.SETTLED, created_at=now - 90*86400)
        recent = PerformanceRecord(record_id="r2", status=TaskStatus.SETTLED, created_at=now - 86400)

        result = apply_decay_to_records([old, recent], SHORT_HALF_LIFE, now)
        _, old_w = result[0]
        _, recent_w = result[1]
        assert recent_w > old_w
