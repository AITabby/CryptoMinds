"""
只读桥接测试
"""

import pytest
import sqlite3
import time
import json
from decimal import Decimal

from credit_score.bridge import CreditScoreBridge


@pytest.fixture
def temp_db(tmp_path):
    """创建一个临时数据库，填入测试数据"""
    db_path = str(tmp_path / "test_cryptominds.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
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
        );

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
        );

        CREATE TABLE IF NOT EXISTS escrow_orders (
            escrow_id TEXT PRIMARY KEY,
            seller_wallet TEXT,
            buyer_wallet TEXT,
            amount TEXT,
            chain TEXT DEFAULT 'bsc',
            state TEXT DEFAULT 'created',
            created_at INTEGER,
            seller_agent_id TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS session_keys (
            session_key_id TEXT PRIMARY KEY,
            main_wallet TEXT NOT NULL,
            agent_id TEXT NOT NULL
        );
    """)

    now = int(time.time())

    # 插入测试数据
    conn.execute(
        "INSERT INTO performance_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("r1", "t1", "token_delivery", "0xbuyer1", "0xseller1", "agent-1", "bsc", "1.0",
         "settled", 1, 0.9, now - 86400, now - 80000, 1000, "tx1", "1.0", "{}", 0, "", ""),
    )
    conn.execute(
        "INSERT INTO performance_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("r2", "t2", "data_delivery", "0xbuyer2", "0xseller1", "agent-1", "solana", "0.5",
         "settled", 1, 0.85, now - 172800, now - 170000, 2000, "tx2", "0.5", "{}", 0, "", ""),
    )
    conn.execute(
        "INSERT INTO performance_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("r3", "t3", "token_delivery", "0xbuyer1", "0xseller2", "agent-2", "bsc", "2.0",
         "failed", 0, 0.0, now - 86400, now - 80000, 5000, "", "0.0", "{}", 1, "bad quality", "buyer_win"),
    )

    # 信用货币
    conn.execute(
        "INSERT INTO credit_currencies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("cur1", "agent-1", "0xseller1", "TestCoin", "TST", "1000", "bsc", 1, now, json.dumps(["agent-2", "agent-3"])),
    )

    # Escrow
    conn.execute(
        "INSERT INTO escrow_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("esc1", "0xseller1", "0xbuyer1", "1.0", "bsc", "released", now, "agent-1"),
    )

    # Session key
    conn.execute(
        "INSERT INTO session_keys VALUES (?, ?, ?)",
        ("sk1", "0xseller1", "agent-1"),
    )

    conn.commit()
    conn.close()

    return db_path


class TestCreditScoreBridge:

    def test_get_records_by_seller(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        records = bridge.get_records_by_seller("0xseller1")
        assert len(records) == 2
        assert records[0]["seller_wallet"] == "0xseller1"

    def test_get_records_by_buyer(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        records = bridge.get_records_by_buyer("0xbuyer1")
        assert len(records) == 2

    def test_get_records_nonexistent(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        records = bridge.get_records_by_seller("0xnonexistent")
        assert len(records) == 0

    def test_get_credit_currencies(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        currencies = bridge.get_credit_currencies()
        assert len(currencies) == 1
        assert currencies[0]["symbol"] == "TST"

    def test_get_credit_acceptance(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        result = bridge.get_credit_acceptance("agent-1")
        assert result["issued_count"] == 1
        assert result["accepted_count"] == 2

    def test_get_accepted_by_agent(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        count = bridge.get_accepted_by_agent("agent-2")
        assert count == 1

    def test_get_agent_wallet(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        wallet = bridge.get_agent_wallet("agent-1")
        assert wallet == "0xseller1"

    def test_get_unique_counterparts(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        count = bridge.get_unique_counterparts("0xseller1")
        assert count >= 2  # buyer1 + buyer2

    def test_get_chain_coverage(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        chains = bridge.get_chain_coverage("0xseller1")
        assert len(chains) == 2
        assert "bsc" in chains
        assert "solana" in chains

    def test_get_all_agent_wallets(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        wallets = bridge.get_all_agent_wallets()
        assert len(wallets) >= 2

    def test_records_to_performance_records(self, temp_db):
        bridge = CreditScoreBridge(db_path=temp_db)
        records = bridge.get_records_by_seller("0xseller1")
        perf_records = bridge.records_to_performance_records(records)
        assert len(perf_records) == 2
        from reputation.record import PerformanceRecord
        assert isinstance(perf_records[0], PerformanceRecord)
