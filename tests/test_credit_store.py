"""
测试信用分存储
"""

import pytest
import tempfile
import os
import time
from src.credit.store import CreditScoreStore
from src.credit.models import (
    SacredScore, DimensionScore, QueryAuthorization,
    PerformanceRecord, TaskStatus
)


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

    def test_verify_authorization_nonexistent(self, store):
        """测试验证不存在的授权"""
        valid = store.verify_authorization("nonexistent", "anyone")
        assert valid is False

    def test_list_authorizations(self, store):
        """测试列出授权"""
        auth = QueryAuthorization(
            auth_id="list_auth_001",
            agent_id="list_agent",
            querier_id="querier_001",
            signature="sig",
            expires_at=int(time.time()) + 3600,
            created_at=int(time.time()),
        )
        store.save_authorization(auth)

        auths = store.list_authorizations("list_agent")
        assert len(auths) == 1
        assert auths[0].auth_id == "list_auth_001"

    def test_get_score_statistics_empty(self, store):
        """测试空数据库的统计"""
        stats = store.get_score_statistics()
        assert stats["total_agents"] == 0
        assert stats["avg_score"] == 0

    def test_get_score_statistics(self, store):
        """测试分数统计"""
        for i, (agent_id, score_val, grade) in enumerate([
            ("stat_agent_a", 800, "AAA"),
            ("stat_agent_b", 600, "BBB"),
            ("stat_agent_c", 400, "CCC"),
        ]):
            score = SacredScore(
                agent_id=agent_id,
                wallet=f"0x{i:040d}",
                stability=DimensionScore("S", "Stability", weighted_score=score_val / 5),
                activity=DimensionScore("A", "Activity", weighted_score=score_val / 5),
                creditworthiness=DimensionScore("C", "Creditworthiness", weighted_score=score_val / 5),
                reliability=DimensionScore("R", "Reliability", weighted_score=score_val / 5),
                ecosystem=DimensionScore("E", "Ecosystem", weighted_score=score_val / 5),
                calculated_at=int(time.time()),
            )
            score.total_score = score_val
            score.grade = grade
            store.save_score(score)

        stats = store.get_score_statistics()
        assert stats["total_agents"] == 3
        assert "grade_counts" in stats

    def test_leaderboard_with_grade_filter(self, store):
        """测试按等级过滤排行榜"""
        for i, (agent_id, score_val, grade) in enumerate([
            ("aaa_agent", 900, "AAA"),
            ("bbb_agent", 600, "BBB"),
        ]):
            score = SacredScore(
                agent_id=agent_id,
                wallet=f"0x{i:040d}",
                stability=DimensionScore("S", "Stability", weighted_score=score_val / 5),
                activity=DimensionScore("A", "Activity", weighted_score=score_val / 5),
                creditworthiness=DimensionScore("C", "Creditworthiness", weighted_score=score_val / 5),
                reliability=DimensionScore("R", "Reliability", weighted_score=score_val / 5),
                ecosystem=DimensionScore("E", "Ecosystem", weighted_score=score_val / 5),
                calculated_at=int(time.time()),
            )
            score.total_score = score_val
            score.grade = grade
            store.save_score(score)

        aaa_only = store.get_leaderboard(limit=10, grade="AAA")
        assert len(aaa_only) == 1
        assert aaa_only[0]["grade"] == "AAA"

    def test_severe_violation(self, store):
        """测试严重违约记录"""
        store.record_severe_violation(
            agent_id="bad_agent",
            wallet="0xbad",
            record_id="rec_001",
            violation_type="buyer_win",
            penalty_points=0.3,
            occurred_at=int(time.time()),
        )

        violations = store.get_severe_violations("bad_agent")
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "buyer_win"

    def test_performance_record(self, store):
        """测试履约记录"""
        record = PerformanceRecord(
            record_id="perf_001",
            task_id="task_001",
            task_type="escrow",
            buyer_wallet="0xbuyer",
            seller_wallet="0xseller",
            seller_agent_id="seller_agent",
            chain="bsc",
            amount="1.0",
            status=TaskStatus.SETTLED,
            success=True,
            score=1.0,
            created_at=int(time.time()),
        )

        store.save_performance_record(record)

        # 按 Agent ID 获取
        records = store.get_performance_records(agent_id="seller_agent")
        assert len(records) == 1
        assert records[0].seller_agent_id == "seller_agent"

        # 按钱包获取
        records = store.get_performance_records(wallet="0xbuyer")
        assert len(records) == 1

    def test_close(self, store):
        """测试关闭（无操作）"""
        store.close()  # 应该不报错
