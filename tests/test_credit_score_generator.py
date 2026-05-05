"""
模拟数据生成器测试
"""

import pytest
import sqlite3
import time

from credit_score.generator import CreditScoreDataGenerator
from credit_score.store import CreditScoreStore


@pytest.fixture
def temp_dbs(tmp_path):
    """创建临时数据库路径"""
    return {
        "db_path": str(tmp_path / "test_sim_cryptominds.db"),
        "credit_db_path": str(tmp_path / "test_sim_credit_score.db"),
    }


class TestCreditScoreDataGenerator:

    def test_generate_agents_count(self, temp_dbs):
        """生成 200 个 Agent"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
            seed=123,
        )
        agents = gen._generate_agents()
        assert len(agents) == 200

    def test_generate_agents_tier_distribution(self, temp_dbs):
        """档位分布大致正确"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
        )
        agents = gen._generate_agents()
        tiers = {}
        for a in agents:
            tiers[a["tier"]] = tiers.get(a["tier"], 0) + 1
        assert tiers["顶级"] >= 15
        assert tiers["劣迹"] >= 25

    def test_generate_records(self, temp_dbs):
        """生成交易记录"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
        )
        gen._agents = gen._generate_agents()
        records = gen._generate_records()
        assert len(records) > 1000  # 200 agent，平均15个任务
        assert len(records) < 10000

    def test_records_have_chains(self, temp_dbs):
        """记录覆盖 3 条链"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
        )
        gen._agents = gen._generate_agents()
        records = gen._generate_records()
        chains = set(r["chain"] for r in records)
        assert len(chains) == 3

    def test_records_time_span(self, temp_dbs):
        """时间跨度约 180 天"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
        )
        gen._agents = gen._generate_agents()
        records = gen._generate_records()
        if records:
            now = int(time.time())
            oldest = min(r["created_at"] for r in records)
            newest = max(r["created_at"] for r in records)
            span_days = (newest - oldest) / 86400
            assert span_days > 30  # 至少跨30天

    def test_full_generation(self, temp_dbs):
        """完整生成流程"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
            seed=42,
        )

        # 初始化表
        conn = sqlite3.connect(temp_dbs["db_path"])
        conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_records (
                record_id TEXT PRIMARY KEY,
                task_id TEXT,
                task_type TEXT,
                buyer_wallet TEXT,
                seller_wallet TEXT,
                seller_agent_id TEXT,
                chain TEXT,
                amount TEXT,
                status TEXT DEFAULT 'pending',
                success INTEGER DEFAULT 0,
                score REAL DEFAULT 0,
                created_at INTEGER,
                completed_at INTEGER,
                response_time_ms INTEGER DEFAULT 0,
                payment_tx TEXT,
                payment_amount TEXT,
                evidence TEXT,
                disputed INTEGER DEFAULT 0,
                dispute_reason TEXT DEFAULT '',
                resolution TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credit_currencies (
                currency_id TEXT PRIMARY KEY,
                issuer_agent_id TEXT,
                issuer_wallet TEXT,
                name TEXT,
                symbol TEXT,
                max_supply TEXT,
                backed_by TEXT,
                active INTEGER DEFAULT 1,
                created_at INTEGER,
                accepted_by TEXT
            )
        """)
        conn.commit()
        conn.close()

        stats = gen.generate()

        assert stats["total_agents"] == 200
        assert stats["total_records"] > 1000
        assert len(stats["grade_distribution"]) > 0

        # 验证数据库中有记录
        conn = sqlite3.connect(temp_dbs["db_path"])
        count = conn.execute("SELECT COUNT(*) FROM performance_records").fetchone()[0]
        conn.close()
        assert count > 0

        # 验证信用分数据库中有分数
        store = CreditScoreStore(db_path=temp_dbs["credit_db_path"])
        lb = store.get_leaderboard(limit=10)
        assert len(lb) > 0

    def test_deterministic_with_seed(self, temp_dbs):
        """相同 seed 生成相同数据"""
        gen1 = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
            seed=42,
        )
        gen2 = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
            seed=42,
        )
        agents1 = gen1._generate_agents()
        agents2 = gen2._generate_agents()
        assert len(agents1) == len(agents2)
        assert agents1[0]["agent_id"] == agents2[0]["agent_id"]
        assert agents1[0]["wallet"] == agents2[0]["wallet"]

    def test_get_statistics(self, temp_dbs):
        """统计摘要"""
        gen = CreditScoreDataGenerator(
            db_path=temp_dbs["db_path"],
            credit_db_path=temp_dbs["credit_db_path"],
        )
        gen._stats = {"total_agents": 200, "total_records": 3000}
        stats = gen.get_statistics()
        assert stats["total_agents"] == 200
