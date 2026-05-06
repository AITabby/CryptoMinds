"""
测试信用分模型
"""

import pytest
from src.credit.models import SacredScore, DimensionScore, CreditGrade


class TestDimensionScore:
    """维度分数测试"""

    def test_create_dimension_score(self):
        """测试创建维度分数"""
        dim = DimensionScore(
            dimension="S",
            name="Security",
            raw_score=85,
            weighted_score=170
        )
        assert dim.dimension == "S"
        assert dim.name == "Security"
        assert dim.raw_score == 85
        assert dim.weighted_score == 170

    def test_dimension_to_dict(self):
        """测试维度转字典"""
        dim = DimensionScore(
            dimension="A",
            name="Availability",
            raw_score=90,
            weighted_score=180
        )
        d = dim.to_dict()
        assert d["dimension"] == "A"
        assert d["name"] == "Availability"
        assert d["score"] == 180.0

    def test_dimension_default(self):
        """测试默认维度"""
        dim = DimensionScore("S", "Stability")
        assert dim.dimension == "S"
        assert dim.raw_score == 0.0


class TestSacredScore:
    """SACRED 分数测试"""

    def test_create_score_default(self):
        """测试创建默认分数"""
        score = SacredScore(
            agent_id="test_agent",
            wallet="0x1234567890123456789012345678901234567890"
        )
        assert score.agent_id == "test_agent"
        assert score.total_score == 0.0
        assert score.grade == "C"

    def test_score_dimensions(self):
        """测试分数维度"""
        score = SacredScore(
            agent_id="test_agent",
            wallet="0x1234567890123456789012345678901234567890",
            stability=DimensionScore("S", "Stability", raw_score=90, weighted_score=180),
            activity=DimensionScore("A", "Activity", raw_score=85, weighted_score=170),
        )
        dims = score.dimensions
        assert "S" in dims
        assert "A" in dims
        assert dims["S"].weighted_score == 180

    def test_compute_total(self):
        """测试计算总分"""
        score = SacredScore(
            agent_id="test_agent",
            wallet="0x1234567890123456789012345678901234567890",
            stability=DimensionScore("S", "Stability", weighted_score=180),
            activity=DimensionScore("A", "Activity", weighted_score=170),
            creditworthiness=DimensionScore("C", "Creditworthiness", weighted_score=160),
            reliability=DimensionScore("R", "Reliability", weighted_score=176),
            ecosystem=DimensionScore("E", "Ecosystem", weighted_score=164),
        )
        total = score.compute_total()
        assert total == 850.0
        # 850 >= 850 threshold for AAA
        assert score.grade == "AAA"

    def test_score_to_dict(self):
        """测试分数转字典"""
        score = SacredScore(
            agent_id="test_agent",
            wallet="0x1234567890123456789012345678901234567890",
            total_score=850,
            grade="AA"
        )
        d = score.to_dict()
        assert d["agent_id"] == "test_agent"
        assert d["total_score"] == 850
        assert d["grade"] == "AA"


class TestCreditGrade:
    """信用等级测试"""

    def test_grade_values(self):
        """测试等级值"""
        assert CreditGrade.AAA.value == "AAA"
        assert CreditGrade.AA.value == "AA"
        assert CreditGrade.A.value == "A"
        assert CreditGrade.BBB.value == "BBB"
        assert CreditGrade.BB.value == "BB"
        assert CreditGrade.B.value == "B"
        assert CreditGrade.C.value == "C"

    def test_grade_from_score(self):
        """测试从分数获取等级"""
        # AAA: >= 850
        grade = CreditGrade.from_score(900)
        assert grade == CreditGrade.AAA

        # AA: >= 750
        grade = CreditGrade.from_score(800)
        assert grade == CreditGrade.AA

        # C: < 150
        grade = CreditGrade.from_score(100)
        assert grade == CreditGrade.C