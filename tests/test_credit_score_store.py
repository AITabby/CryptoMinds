"""
信用分存储测试
"""

import pytest
import time

from credit_score.store import CreditScoreStore
from credit_score.models import SacredScore, DimensionScore, QueryAuthorization, ScoreHistoryEntry


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_credit_score.db")
    return CreditScoreStore(db_path=db_path)


def _make_score(agent_id="agent-1", wallet="0xabc", total=750, grade="A", cold_start=False):
    now = int(time.time())
    score = SacredScore(agent_id=agent_id, wallet=wallet, calculated_at=now, is_cold_start=cold_start)
    per_dim = total / 5
    for d in score.dimensions.values():
        d.raw_score = per_dim
        d.weighted_score = per_dim
    score.total_score = total
    score.grade = grade
    score.compute_hash()
    return score


class TestCreditScoreStore:

    def test_save_and_get_score(self, store):
        score = _make_score()
        store.save_score(score)

        result = store.get_latest_score("agent-1")
        assert result is not None
        assert result.agent_id == "agent-1"
        assert result.total_score == 750
        assert result.grade == "A"

    def test_get_nonexistent_score(self, store):
        result = store.get_latest_score("nonexistent")
        assert result is None

    def test_dimension_details_saved(self, store):
        score = _make_score()
        score.stability.components = {"success_rate": 90.5, "timeout": 55.0}
        store.save_score(score)

        result = store.get_latest_score("agent-1")
        assert result.stability.components["success_rate"] == 90.5

    def test_score_history(self, store):
        # 保存两个不同时间的分数
        score1 = _make_score()
        score1.calculated_at = int(time.time()) - 100
        store.save_score(score1)

        score2 = _make_score(total=800, grade="AA")
        score2.calculated_at = int(time.time())  # 不同时间戳
        store.save_score(score2)

        history = store.get_score_history("agent-1")
        assert len(history) == 2
        # 最新的在前
        assert history[0].score == 800

    def test_authorization_create_and_verify(self, store):
        now = int(time.time())
        auth = QueryAuthorization(
            auth_id="auth-1",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xsig",
            expires_at=now + 3600,
            created_at=now,
        )
        store.save_authorization(auth)

        assert store.verify_authorization("auth-1", "agent-2") is True

    def test_authorization_expired(self, store):
        now = int(time.time())
        auth = QueryAuthorization(
            auth_id="auth-2",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xsig",
            expires_at=now - 1,  # 已过期
            created_at=now - 7200,
        )
        store.save_authorization(auth)

        assert store.verify_authorization("auth-2", "agent-2") is False

    def test_authorization_wrong_querier(self, store):
        now = int(time.time())
        auth = QueryAuthorization(
            auth_id="auth-3",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xsig",
            expires_at=now + 3600,
            created_at=now,
        )
        store.save_authorization(auth)

        assert store.verify_authorization("auth-3", "agent-3") is False

    def test_authorization_revoke(self, store):
        now = int(time.time())
        auth = QueryAuthorization(
            auth_id="auth-4",
            agent_id="agent-1",
            querier_id="agent-2",
            signature="0xsig",
            expires_at=now + 3600,
            created_at=now,
        )
        store.save_authorization(auth)

        assert store.verify_authorization("auth-4", "agent-2") is True
        store.revoke_authorization("auth-4")
        assert store.verify_authorization("auth-4", "agent-2") is False

    def test_list_authorizations(self, store):
        now = int(time.time())
        for i in range(3):
            auth = QueryAuthorization(
                auth_id=f"auth-list-{i}",
                agent_id="agent-1",
                querier_id=f"agent-{i+10}",
                signature="0xsig",
                expires_at=now + 3600,
                created_at=now,
            )
            store.save_authorization(auth)

        auths = store.list_authorizations("agent-1")
        assert len(auths) == 3

    def test_leaderboard(self, store):
        for i in range(5):
            score = _make_score(agent_id=f"agent-{i}", wallet=f"0x{i}", total=500 + i * 100)
            store.save_score(score)

        lb = store.get_leaderboard(limit=10)
        assert len(lb) == 5
        assert lb[0]["total_score"] >= lb[1]["total_score"]

    def test_leaderboard_with_grade_filter(self, store):
        for i in range(5):
            total = 500 + i * 100
            grade = "A" if total >= 700 else "BB"
            score = _make_score(agent_id=f"agent-{i}", wallet=f"0x{i}", total=total, grade=grade)
            store.save_score(score)

        lb = store.get_leaderboard(grade="A")
        for entry in lb:
            assert entry["grade"] == "A"

    def test_severe_violations(self, store):
        store.record_severe_violation("agent-1", "0xabc", "r1", "seller_win", 50, int(time.time()))
        violations = store.get_severe_violations("agent-1")
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "seller_win"

    def test_cold_start_flag(self, store):
        score = _make_score(cold_start=True)
        store.save_score(score)

        result = store.get_latest_score("agent-1")
        assert result.is_cold_start is True
