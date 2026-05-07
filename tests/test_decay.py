"""
时间衰减测试
"""

import time

from src.credit.decay import (
    time_decay,
    days_between,
    apply_decay_to_records,
    no_decay_violation,
    weighted_success_rate,
)
from src.credit.models import PerformanceRecord, TaskStatus


class TestTimeDecay:
    """时间衰减函数测试"""

    def test_time_decay_zero_days(self):
        """测试 0 天前"""
        assert time_decay(0, 90) == 1.0

    def test_time_decay_one_half_life(self):
        """测试一个半衰期"""
        # 90 天半衰期，90 天后权重应为 0.5
        result = time_decay(90, 90)
        assert abs(result - 0.5) < 0.01

    def test_time_decay_two_half_lives(self):
        """测试两个半衰期"""
        # 180 天后权重应为 0.25
        result = time_decay(180, 90)
        assert abs(result - 0.25) < 0.01

    def test_time_decay_negative_days(self):
        """测试负天数（未来时间）"""
        assert time_decay(-10, 90) == 1.0

    def test_time_decay_long_ago(self):
        """测试很久以前"""
        # 360 天前（4个半衰期），权重应约为 0.0625
        result = time_decay(360, 90)
        assert result < 0.1
        assert result > 0.05


class TestDaysBetween:
    """天数计算测试"""

    def test_days_between_now(self):
        """测试当前时间"""
        now = int(time.time())
        assert days_between(now, now) == 0.0

    def test_days_between_one_day(self):
        """测试一天前"""
        now = int(time.time())
        one_day_ago = now - 86400
        assert days_between(one_day_ago, now) == 1.0

    def test_days_between_week(self):
        """测试一周前"""
        now = int(time.time())
        week_ago = now - 7 * 86400
        assert days_between(week_ago, now) == 7.0

    def test_days_between_future(self):
        """测试未来时间"""
        now = int(time.time())
        future = now + 86400
        assert days_between(future, now) == 0.0


class TestNoDecayViolation:
    """严重违约判断测试"""

    def test_seller_win_is_severe(self):
        """测试 seller_win 是严重违约"""
        assert no_decay_violation("seller_win") is True

    def test_timeout_is_severe(self):
        """测试 timeout 是严重违约"""
        assert no_decay_violation("timeout") is True

    def test_buyer_win_not_severe(self):
        """测试 buyer_win 不是严重违约"""
        assert no_decay_violation("buyer_win") is False

    def test_settled_not_severe(self):
        """测试 settled 不是严重违约"""
        assert no_decay_violation("settled") is False


class TestApplyDecayToRecords:
    """记录衰减测试"""

    def test_apply_decay_empty(self):
        """测试空记录"""
        result = apply_decay_to_records([], 90)
        assert result == []

    def test_apply_decay_single_record(self):
        """测试单条记录"""
        now = int(time.time())
        record = PerformanceRecord(
            record_id="test_1",
            task_id="task_1",
            task_type="test",
            buyer_wallet="0x1",
            seller_wallet="0x2",
            seller_agent_id="agent_1",
            chain="bsc",
            amount="1.0",
            status=TaskStatus.SETTLED,
            success=True,
            score=1.0,
            created_at=now - 86400,  # 1天前
        )

        result = apply_decay_to_records([record], 90, now)
        assert len(result) == 1
        assert result[0][0] == record
        assert 0.99 < result[0][1] <= 1.0  # 1天前的权重应接近 1


class TestWeightedSuccessRate:
    """加权成功率测试"""

    def test_empty_records(self):
        """测试空记录"""
        assert weighted_success_rate([]) == 0.0

    def test_all_success(self):
        """测试全部成功"""
        now = int(time.time())
        records = []
        for i in range(5):
            records.append(PerformanceRecord(
                record_id=f"test_{i}",
                task_id=f"task_{i}",
                task_type="test",
                buyer_wallet="0x1",
                seller_wallet="0x2",
                seller_agent_id="agent_1",
                chain="bsc",
                amount="1.0",
                status=TaskStatus.SETTLED,
                success=True,
                score=1.0,
                created_at=now - i * 86400,  # 0-4 天前
            ))

        rate = weighted_success_rate(records, now)
        assert rate == 1.0

    def test_all_failed(self):
        """测试全部失败"""
        now = int(time.time())
        records = []
        for i in range(5):
            records.append(PerformanceRecord(
                record_id=f"test_{i}",
                task_id=f"task_{i}",
                task_type="test",
                buyer_wallet="0x1",
                seller_wallet="0x2",
                seller_agent_id="agent_1",
                chain="bsc",
                amount="1.0",
                status=TaskStatus.REFUNDED,
                success=False,
                score=0.0,
                created_at=now - i * 86400,
            ))

        rate = weighted_success_rate(records, now)
        assert rate == 0.0

    def test_mixed_records(self):
        """测试混合记录"""
        now = int(time.time())

        # 2 成功 + 2 失败
        records = [
            PerformanceRecord(
                record_id="s1", task_id="t1", task_type="test",
                buyer_wallet="0x1", seller_wallet="0x2", seller_agent_id="agent_1",
                chain="bsc", amount="1.0", status=TaskStatus.SETTLED,
                success=True, score=1.0, created_at=now - 86400,
            ),
            PerformanceRecord(
                record_id="s2", task_id="t2", task_type="test",
                buyer_wallet="0x1", seller_wallet="0x2", seller_agent_id="agent_1",
                chain="bsc", amount="1.0", status=TaskStatus.SETTLED,
                success=True, score=1.0, created_at=now - 86400 * 2,
            ),
            PerformanceRecord(
                record_id="f1", task_id="t3", task_type="test",
                buyer_wallet="0x1", seller_wallet="0x2", seller_agent_id="agent_1",
                chain="bsc", amount="1.0", status=TaskStatus.REFUNDED,
                success=False, score=0.0, created_at=now - 86400 * 3,
            ),
            PerformanceRecord(
                record_id="f2", task_id="t4", task_type="test",
                buyer_wallet="0x1", seller_wallet="0x2", seller_agent_id="agent_1",
                chain="bsc", amount="1.0", status=TaskStatus.REFUNDED,
                success=False, score=0.0, created_at=now - 86400 * 4,
            ),
        ]

        rate = weighted_success_rate(records, now)
        # 近期成功的权重更高，所以成功率应大于 0.5
        assert 0.5 < rate < 1.0
