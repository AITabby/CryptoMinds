"""
SACRED 信用分模型测试
"""

import pytest
import time

from credit_score.models import (
    SacredScore, DimensionScore, CreditGrade,
    QueryAuthorization, ScoreHistoryEntry,
)
from credit_score.config import DIMENSION_MAX, TOTAL_MAX


class TestDimensionScore:
    """维度评分测试"""

    def test_to_dict(self):
        ds = DimensionScore("S", "Stability", 180.0, 175.5, {"success_rate": 90.0})
        d = ds.to_dict()
        assert d["dimension"] == "S"
        assert d["name"] == "Stability"
        assert d["score"] == 175.5
        assert d["max"] == DIMENSION_MAX
        assert d["components"]["success_rate"] == 90.0

    def test_from_dict(self):
        data = {"dimension": "A", "name": "Activity", "raw_score": 150, "weighted_score": 140, "components": {"recent": 80}}
        ds = DimensionScore.from_dict(data)
        assert ds.dimension == "A"
        assert ds.name == "Activity"
        assert ds.raw_score == 150
        assert ds.weighted_score == 140
        assert ds.components["recent"] == 80

    def test_roundtrip(self):
        ds = DimensionScore("R", "Reliability", 120.0, 115.3, {"dispute": 70.0, "violation": 45.3})
        d = ds.to_dict()
        ds2 = DimensionScore.from_dict({
            "dimension": d["dimension"],
            "name": d["name"],
            "raw_score": 120.0,
            "weighted_score": 115.3,
            "components": d["components"],
        })
        assert ds2.dimension == ds.dimension
        assert ds2.weighted_score == ds.weighted_score

    def test_default_values(self):
        ds = DimensionScore("E", "Ecosystem")
        assert ds.raw_score == 0.0
        assert ds.weighted_score == 0.0
        assert ds.components == {}


class TestCreditGrade:
    """信用等级测试"""

    def test_aaa(self):
        assert CreditGrade.from_score(900) == CreditGrade.AAA
        assert CreditGrade.from_score(850) == CreditGrade.AAA

    def test_aa(self):
        assert CreditGrade.from_score(849) == CreditGrade.AA
        assert CreditGrade.from_score(750) == CreditGrade.AA

    def test_a(self):
        assert CreditGrade.from_score(749) == CreditGrade.A
        assert CreditGrade.from_score(650) == CreditGrade.A

    def test_bbb(self):
        assert CreditGrade.from_score(649) == CreditGrade.BBB
        assert CreditGrade.from_score(550) == CreditGrade.BBB

    def test_bb(self):
        assert CreditGrade.from_score(549) == CreditGrade.BB
        assert CreditGrade.from_score(450) == CreditGrade.BB

    def test_b(self):
        assert CreditGrade.from_score(449) == CreditGrade.B
        assert CreditGrade.from_score(350) == CreditGrade.B

    def test_ccc(self):
        assert CreditGrade.from_score(349) == CreditGrade.CCC
        assert CreditGrade.from_score(250) == CreditGrade.CCC

    def test_cc(self):
        assert CreditGrade.from_score(249) == CreditGrade.CC
        assert CreditGrade.from_score(150) == CreditGrade.CC

    def test_c(self):
        assert CreditGrade.from_score(149) == CreditGrade.C
        assert CreditGrade.from_score(0) == CreditGrade.C


class TestSacredScore:
    """SACRED 总分测试"""

    def test_compute_total(self):
        score = SacredScore()
        score.stability.weighted_score = 180
        score.activity.weighted_score = 150
        score.creditworthiness.weighted_score = 160
        score.reliability.weighted_score = 140
        score.ecosystem.weighted_score = 130
        total = score.compute_total()
        assert total == 760.0
        assert score.grade == "AA"

    def test_compute_total_capped(self):
        score = SacredScore()
        for d in score.dimensions.values():
            d.weighted_score = 250  # 超过 200
        score.compute_total()
        assert score.total_score == TOTAL_MAX
        assert score.grade == "AAA"

    def test_compute_total_zero(self):
        score = SacredScore()
        score.compute_total()
        assert score.total_score == 0.0
        assert score.grade == "C"

    def test_compute_hash(self):
        score = SacredScore(agent_id="test", wallet="0xabc")
        score.stability.weighted_score = 100
        score.compute_total()
        h = score.compute_hash()
        assert len(h) == 16
        # 同样输入同样哈希
        h2 = score.compute_hash()
        assert h == h2

    def test_to_dict_from_dict(self):
        score = SacredScore(agent_id="agent-1", wallet="0x123")
        score.stability = DimensionScore("S", "Stability", 180, 175, {"s": 90})
        score.activity = DimensionScore("A", "Activity", 150, 140, {"a": 70})
        score.creditworthiness = DimensionScore("C", "Creditworthiness", 160, 155, {"c": 80})
        score.reliability = DimensionScore("R", "Reliability", 140, 135, {"r": 60})
        score.ecosystem = DimensionScore("E", "Ecosystem", 130, 125, {"e": 50})
        score.compute_total()
        score.compute_hash()

        d = score.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["total_score"] == 730.0
        assert d["grade"] == "A"
        assert "S" in d["dimensions"]

        score2 = SacredScore.from_dict(d)
        assert score2.agent_id == "agent-1"
        assert score2.total_score == 730.0

    def test_dimensions_property(self):
        score = SacredScore()
        dims = score.dimensions
        assert len(dims) == 5
        assert "S" in dims
        assert "A" in dims
        assert "C" in dims
        assert "R" in dims
        assert "E" in dims


class TestQueryAuthorization:
    """查询授权测试"""

    def test_not_expired(self):
        auth = QueryAuthorization(
            auth_id="auth-1",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xabc",
            expires_at=int(time.time()) + 3600,
            created_at=int(time.time()),
        )
        assert not auth.is_expired

    def test_expired(self):
        auth = QueryAuthorization(
            auth_id="auth-1",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xabc",
            expires_at=int(time.time()) - 1,
            created_at=int(time.time()) - 7200,
        )
        assert auth.is_expired

    def test_to_dict(self):
        auth = QueryAuthorization(auth_id="auth-1", agent_id="a1", querier_id="a2")
        d = auth.to_dict()
        assert d["auth_id"] == "auth-1"
        assert d["agent_id"] == "a1"


class TestScoreHistoryEntry:
    def test_to_dict(self):
        entry = ScoreHistoryEntry(
            agent_id="a1", score=750, grade="A",
            dimension_scores={"S": 180, "A": 150}, calculated_at=1000,
        )
        d = entry.to_dict()
        assert d["score"] == 750
        assert d["grade"] == "A"
        assert d["dimension_scores"]["S"] == 180
