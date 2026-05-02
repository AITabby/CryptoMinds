"""PostgreSQL store 测试 — 需要 DATABASE_URL 环境变量指向测试 PG 实例"""

import os
import pytest
from decimal import Decimal

# Skip entire module if no PG available
PG_URL = os.getenv("DATABASE_URL", "")
if not PG_URL or not PG_URL.startswith(("postgres://", "postgresql://")):
    pytest.skip("DATABASE_URL not set, skipping PG tests", allow_module_level=True)

# Verify connection
try:
    import psycopg2
    psycopg2.connect(PG_URL)
    PG_AVAILABLE = True
except Exception:
    pytest.skip("psycopg2 cannot connect, skipping PG tests", allow_module_level=True)


# ── Record Store ────────────────────────────────────────────

class TestPgRecordStore:
    def test_save_and_get(self):
        from data.pg_store import PgRecordStore
        from reputation.record import PerformanceRecord, TaskStatus
        store = PgRecordStore(PG_URL)
        record = PerformanceRecord(
            record_id="pg-test-1",
            task_id="task-pg-1",
            task_type="token_delivery",
            buyer_wallet="0xBuyer",
            seller_wallet="0xSeller",
            seller_agent_id="agent-pg",
            chain="bsc",
            amount=Decimal("0.5"),
            status=TaskStatus.COMPLETED,
            success=True,
            score=0.95,
            created_at=1000,
            completed_at=1100,
            response_time_ms=100,
        )
        store.save(record)
        got = store.get("pg-test-1")
        assert got is not None
        assert got.record_id == "pg-test-1"
        assert got.success is True
        assert got.score == 0.95

    def test_get_by_seller(self):
        from data.pg_store import PgRecordStore
        from reputation.record import PerformanceRecord, TaskStatus
        store = PgRecordStore(PG_URL)
        record = PerformanceRecord(
            record_id="pg-seller-1",
            task_id="task-s",
            task_type="data_delivery",
            seller_wallet="0xSellerPG",
            buyer_wallet="0xBuyerPG",
            chain="mock",
            amount=Decimal("1.0"),
            status=TaskStatus.COMPLETED,
            success=True,
        )
        store.save(record)
        results = store.get_by_seller("0xSellerPG")
        assert len(results) >= 1

    def test_count(self):
        from data.pg_store import PgRecordStore
        store = PgRecordStore(PG_URL)
        assert store.count() >= 0


# ── Escrow Store ────────────────────────────────────────────

class TestPgEscrowStore:
    def test_save_and_get(self):
        from data.pg_store import PgEscrowStore
        from escrow.models import EscrowOrder
        from settlement.escrow_state import EscrowState
        store = PgEscrowStore(PG_URL)
        order = EscrowOrder(
            escrow_id="pg-escrow-1",
            task_id="task-e",
            buyer_wallet="0xB",
            seller_wallet="0xS",
            seller_agent_id="agent-e",
            amount=Decimal("0.5"),
            channel_id="mock",
            chain="mock",
            state=EscrowState.CREATED,
            created_at=1000,
        )
        store.save(order)
        got = store.get("pg-escrow-1")
        assert got is not None
        assert got.escrow_id == "pg-escrow-1"
        assert got.state == EscrowState.CREATED

    def test_get_by_state(self):
        from data.pg_store import PgEscrowStore
        from settlement.escrow_state import EscrowState
        store = PgEscrowStore(PG_URL)
        results = store.get_by_state(EscrowState.CREATED)
        assert isinstance(results, list)


# ── Session Key Store ────────────────────────────────────────

class TestPgSessionKeyStore:
    def test_save_and_get(self):
        from data.pg_store import PgSessionKeyStore
        from auth.session_key import SessionKey
        store = PgSessionKeyStore(PG_URL)
        key = SessionKey(
            session_key_id="pg-sk-1",
            main_wallet="0xMain",
            agent_id="agent-sk",
            available_chains=["bsc"],
            per_tx_limit=Decimal("1.0"),
            total_quota=Decimal("10.0"),
            total_used=Decimal("0"),
            callable_actions=["pay"],
            created_at=1000,
            expires_at=2000,
            nonce=0,
            revoked=False,
            revoked_at=0,
            session_address="0xSession",
            authorization_signature="sig",
        )
        store.save(key)
        got = store.get("pg-sk-1")
        assert got is not None
        assert got.session_key_id == "pg-sk-1"
        assert got.main_wallet == "0xMain"

    def test_revoke(self):
        from data.pg_store import PgSessionKeyStore
        from auth.session_key import SessionKey
        store = PgSessionKeyStore(PG_URL)
        key = SessionKey(
            session_key_id="pg-sk-rev",
            main_wallet="0xMainRev",
            agent_id="agent-rev",
            available_chains=["bsc"],
            per_tx_limit=Decimal("1.0"),
            total_quota=Decimal("10.0"),
            callable_actions=["pay"],
            created_at=1000,
            expires_at=2000,
            session_address="0xS",
            authorization_signature="sig",
        )
        store.save(key)
        result = store.revoke("pg-sk-rev")
        assert result is True
        got = store.get("pg-sk-rev")
        assert got.revoked is True
        assert got.nonce == 1


# ── Voucher Store ────────────────────────────────────────────

class TestPgVoucherStore:
    def test_save_and_get(self):
        from data.pg_store import PgVoucherStore
        from voucher.models import Voucher
        from voucher.state import VoucherState
        store = PgVoucherStore(PG_URL)
        v = Voucher(
            voucher_id="pg-vch-1",
            issuer_wallet="0xBuyer",
            agent_id="agent-vch",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
        )
        store.save(v)
        got = store.get("pg-vch-1")
        assert got is not None
        assert got.voucher_id == "pg-vch-1"
        assert got.state == VoucherState.ISSUED

    def test_get_by_agent(self):
        from data.pg_store import PgVoucherStore
        from voucher.models import Voucher
        store = PgVoucherStore(PG_URL)
        v = Voucher(
            voucher_id="pg-vch-agent",
            issuer_wallet="0xBuyer",
            agent_id="agent-vch-pg",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=10,
            total_deposit=Decimal("0.1"),
        )
        store.save(v)
        results = store.get_by_agent("agent-vch-pg")
        assert len(results) >= 1


# ── Factory ──────────────────────────────────────────────────

class TestStoreFactory:
    def test_factory_pg(self):
        from data import create_stores
        stores = create_stores()
        # With DATABASE_URL set, should get PG stores
        assert stores["record"].__class__.__name__.startswith("Pg")
        assert stores["escrow"].__class__.__name__.startswith("Pg")