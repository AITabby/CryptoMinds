"""
测试信用分存储
"""

import pytest
import tempfile
import os
from src.credit.store import CreditScoreStore
from src.credit.models import SacredScore, DimensionScore


class TestCreditScoreStore:
    """信用分存储测试"""

    @pytest.fixture
    def store(self):
        """创建临时存储"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = CreditScoreStore(db_path=db_path)
        yield store
        os.unlink(db_path)

    def test_save_and_get_score(self, store):
        """测试保存和获取信用分"""
        score = SacredScore(
            agent_id="test_agent",
            wallet="0x1234567890123456789012345678901234567890",
            stability=DimensionScore("S", "Stability", raw_score=90, weighted_score=180),
            activity=DimensionScore("A", "Activity", raw_score=85, weighted_score=170),
            creditworthiness=DimensionScore("C", "Creditworthiness",
                                            raw_score=80, weighted_score=160),
            reliability=DimensionScore("R", "Reliability", raw_score=88, weighted_score=176),
            ecosystem=DimensionScore("E", "Ecosystem", raw_score=82, weighted_score=164),
        )
        score.compute_total()

        store.save_score(score)
        retrieved = store.get_latest_score("test_agent")

        assert retrieved is not None
        assert retrieved.agent_id == "test_agent"
        assert retrieved.total_score == 850.0

    def test_get_nonexistent_score(self, store):
        """测试获取不存在的信用分"""
        score = store.get_latest_score("nonexistent_agent")
        assert score is None

    def test_score_history(self, store):
        """测试信用分历史"""
        import time
        # 保存多个分数，每个间隔一点时间
        for i in range(3):
            score = SacredScore(
                agent_id="history_agent",
                wallet="0x1234567890123456789012345678901234567890",
                stability=DimensionScore("S", "Stability", weighted_score=160 + i * 5),
                activity=DimensionScore("A", "Activity", weighted_score=160),
                creditworthiness=DimensionScore("C", "Creditworthiness", weighted_score=160),
                reliability=DimensionScore("R", "Reliability", weighted_score=160),
                ecosystem=DimensionScore("E", "Ecosystem", weighted_score=160),
                calculated_at=int(time.time()) + i,  # 确保时间戳不同
            )
            score.compute_total()
            store.save_score(score)
            time.sleep(0.01)  # 确保时间戳不同

        history = store.get_score_history("history_agent", limit=10)
        assert len(history) == 3

    def test_leaderboard(self, store):
        """测试排行榜"""
        # 保存多个 Agent 的分数
        for i in range(5):
            score = SacredScore(
                agent_id=f"agent_{i}",
                wallet=f"0x{i:040d}",
                stability=DimensionScore("S", "Stability", weighted_score=160 + i * 10),
                activity=DimensionScore("A", "Activity", weighted_score=160),
                creditworthiness=DimensionScore("C", "Creditworthiness", weighted_score=160),
                reliability=DimensionScore("R", "Reliability", weighted_score=160),
                ecosystem=DimensionScore("E", "Ecosystem", weighted_score=160),
            )
            score.compute_total()
            store.save_score(score)

        leaderboard = store.get_leaderboard(limit=10)
        assert len(leaderboard) == 5

    def test_save_authorization(self, store):
        """测试保存授权"""
        from src.credit.models import QueryAuthorization
        import time

        auth = QueryAuthorization(
            auth_id="test_auth_123",
            agent_id="test_agent",
            querier_id="querier_123",
            signature="0xabc123",
            expires_at=int(time.time()) + 3600,
            created_at=int(time.time()),
        )

        store.save_authorization(auth)

        # 验证授权
        valid = store.verify_authorization("test_auth_123", "querier_123")
        assert valid is True

    def test_revoke_authorization(self, store):
        """测试撤销授权"""
        from src.credit.models import QueryAuthorization
        import time

        auth = QueryAuthorization(
            auth_id="test_auth_revoke",
            agent_id="test_agent",
            querier_id="querier_123",
            signature="0xabc123",
            expires_at=int(time.time()) + 3600,
            created_at=int(time.time()),
        )
        store.save_authorization(auth)

        # 撤销
        result = store.revoke_authorization("test_auth_revoke")
        assert result is True

        # 验证已撤销
        valid = store.verify_authorization("test_auth_revoke", "querier_123")
        assert valid is False
