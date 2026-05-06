"""
冷启动测试
"""

import pytest

from credit_score.cold_start import ColdStartManager
from credit_score.models import SacredScore, DimensionScore
from credit_score.config import COLD_START_SCORE, COLD_START_THRESHOLD, COLD_START_MAX_BOOST, TOTAL_MAX


class TestColdStartManager:

    def setup_method(self):
        self.mgr = ColdStartManager()

    def test_is_cold_start_zero_tasks(self):
        assert self.mgr.is_cold_start(0) is True

    def test_is_cold_start_below_threshold(self):
        assert self.mgr.is_cold_start(COLD_START_THRESHOLD - 1) is True

    def test_is_cold_start_at_threshold(self):
        assert self.mgr.is_cold_start(COLD_START_THRESHOLD) is False

    def test_is_cold_start_above_threshold(self):
        assert self.mgr.is_cold_start(COLD_START_THRESHOLD + 10) is False

    def test_zero_tasks_returns_cold_start_score(self):
        """0 个任务 -> 初始分 COLD_START_SCORE"""
        score = SacredScore(agent_id="new", wallet="0x")
        for d in score.dimensions.values():
            d.weighted_score = 10  # 真实分很低
        score.compute_total()

        result = self.mgr.apply_cold_start(score, 0)
        assert result.is_cold_start is True
        assert result.total_score == COLD_START_SCORE

    def test_half_way_interpolation(self):
        """5 个任务（一半）-> 介于冷启动和真实分之间"""
        score = SacredScore(agent_id="test", wallet="0x")
        for d in score.dimensions.values():
            d.weighted_score = 200  # 真实分满分
        score.compute_total()

        result = self.mgr.apply_cold_start(score, COLD_START_THRESHOLD // 2)
        assert result.is_cold_start is True
        # 分数应该高于冷启动基础分但低于满分
        assert result.total_score > COLD_START_SCORE
        assert result.total_score < TOTAL_MAX

    def test_above_threshold_no_cold_start(self):
        """超过阈值 -> 不做冷启动调整"""
        score = SacredScore(agent_id="test", wallet="0x")
        for d in score.dimensions.values():
            d.weighted_score = 180
        score.compute_total()

        result = self.mgr.apply_cold_start(score, COLD_START_THRESHOLD + 5)
        assert result.is_cold_start is False

    def test_get_boost_zero(self):
        """0 个任务 -> boost = 0"""
        assert self.mgr.get_boost(0) == 0

    def test_get_boost_at_threshold(self):
        """达到阈值 -> boost = MAX_BOOST"""
        assert self.mgr.get_boost(COLD_START_THRESHOLD) == COLD_START_MAX_BOOST

    def test_get_boost_half_way(self):
        """5 个任务 -> boost = 50"""
        boost = self.mgr.get_boost(COLD_START_THRESHOLD // 2)
        assert boost == COLD_START_MAX_BOOST / 2

    def test_cold_start_score_does_not_exceed_max(self):
        """冷启动分数不超过 1000"""
        score = SacredScore(agent_id="test", wallet="0x")
        for d in score.dimensions.values():
            d.weighted_score = 200
        score.compute_total()

        result = self.mgr.apply_cold_start(score, COLD_START_THRESHOLD - 1)
        assert result.total_score <= 1000

    def test_transition_at_threshold_boundary(self):
        """阈值边界：9 任务 vs 10 任务"""
        score1 = SacredScore(agent_id="test", wallet="0x")
        for d in score1.dimensions.values():
            d.weighted_score = 100
        score1.compute_total()
        result1 = self.mgr.apply_cold_start(score1, COLD_START_THRESHOLD - 1)

        score2 = SacredScore(agent_id="test", wallet="0x")
        for d in score2.dimensions.values():
            d.weighted_score = 100
        score2.compute_total()
        result2 = self.mgr.apply_cold_start(score2, COLD_START_THRESHOLD)

        # 9 个任务还是冷启动，10 个不是
        assert result1.is_cold_start is True
        assert result2.is_cold_start is False
