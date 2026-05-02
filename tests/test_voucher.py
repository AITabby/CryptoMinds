"""
Voucher 按量计费 测试
"""

import os
import time
import pytest
from decimal import Decimal


# ── 状态机 ──────────────────────────────────────────────

class TestVoucherStateMachine:
    def test_initial_state(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        assert sm.state == VoucherState.ISSUED

    def test_legal_transitions(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        sm.transition("activate", timestamp=1, actor="buyer")
        assert sm.state == VoucherState.ACTIVE
        sm.transition("use", timestamp=2, actor="buyer")
        assert sm.state == VoucherState.ACTIVE
        sm.transition("exhaust", timestamp=3, actor="system")
        assert sm.state == VoucherState.EXHAUSTED

    def test_dispute_from_active(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        sm.transition("activate", timestamp=1)
        sm.transition("dispute", timestamp=2, actor="buyer")
        assert sm.state == VoucherState.DISPUTED

    def test_arbitration(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        sm.transition("activate", timestamp=1)
        sm.transition("dispute", timestamp=2)
        sm.transition("arbitrate_buyer_win", timestamp=3, actor="admin")
        assert sm.state == VoucherState.RESOLVED_REFUND

    def test_cancel_from_issued(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        sm.transition("cancel", timestamp=1)
        assert sm.state == VoucherState.CANCELLED

    def test_cancel_from_active(self):
        from voucher.state import VoucherStateMachine, VoucherState
        sm = VoucherStateMachine()
        sm.transition("activate", timestamp=1)
        sm.transition("cancel", timestamp=2)
        assert sm.state == VoucherState.CANCELLED

    def test_illegal_transition(self):
        from voucher.state import VoucherStateMachine, VoucherState, InvalidTransitionError
        sm = VoucherStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.transition("dispute")

    def test_terminal_state_no_transition(self):
        from voucher.state import VoucherStateMachine, VoucherState, InvalidTransitionError
        sm = VoucherStateMachine()
        sm.transition("activate")
        sm.transition("exhaust")
        with pytest.raises(InvalidTransitionError):
            sm.transition("use")

    def test_can_transition(self):
        from voucher.state import VoucherStateMachine
        sm = VoucherStateMachine()
        assert sm.can_transition("activate")
        assert not sm.can_transition("dispute")


# ── 数据模型 ────────────────────────────────────────────

class TestVoucherModel:
    def test_create(self):
        from voucher.models import Voucher
        from voucher.state import VoucherState
        v = Voucher(
            voucher_id="vch-test",
            issuer_wallet="0xBuyer",
            agent_id="agent-test",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
        )
        assert v.state == VoucherState.ISSUED
        assert v.units_remaining == 100
        assert v.remaining_deposit == Decimal("1.0")

    def test_units_remaining(self):
        from voucher.models import Voucher
        v = Voucher(
            voucher_id="vch-test",
            issuer_wallet="0xBuyer",
            agent_id="agent-test",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
            units_used=30,
        )
        assert v.units_remaining == 70
        assert v.remaining_deposit == Decimal("0.7")

    def test_to_dict(self):
        from voucher.models import Voucher
        v = Voucher(
            voucher_id="vch-test",
            issuer_wallet="0xBuyer",
            agent_id="agent-test",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
        )
        d = v.to_dict()
        assert d["voucher_id"] == "vch-test"
        assert d["state"] == "issued"
        assert d["unit_price"] == "0.01"
        assert d["units_remaining"] == 100


# ── 验证器 ──────────────────────────────────────────────

class TestVoucherChainVerifier:
    def test_valid_chain(self):
        from voucher.verifier import VoucherChainVerifier, UsageRecord
        verifier = VoucherChainVerifier()
        records = [
            UsageRecord("v1", 1, 1, 0, 1000),
            UsageRecord("v1", 2, 3, 1, 1001),
            UsageRecord("v1", 5, 8, 3, 1002),
        ]
        result = verifier.verify_chain(records)
        assert result["valid"]
        assert result["total_units_used"] == 8

    def test_cumulative_regression(self):
        from voucher.verifier import VoucherChainVerifier, UsageRecord
        verifier = VoucherChainVerifier()
        records = [
            UsageRecord("v1", 1, 5, 0, 1000),
            UsageRecord("v1", 1, 3, 5, 1001),  # cumulative 回退
        ]
        result = verifier.verify_chain(records)
        assert not result["valid"]

    def test_chain_break(self):
        from voucher.verifier import VoucherChainVerifier, UsageRecord
        verifier = VoucherChainVerifier()
        records = [
            UsageRecord("v1", 1, 1, 0, 1000),
            UsageRecord("v1", 2, 3, 99, 1001),  # previous_cumulative 不匹配
        ]
        result = verifier.verify_chain(records)
        assert not result["valid"]

    def test_overcharge(self):
        from voucher.verifier import VoucherChainVerifier, UsageRecord
        verifier = VoucherChainVerifier()
        records = [
            UsageRecord("v1", 1, 1, 0, 1000),
            UsageRecord("v1", 1, 101, 1, 1001),  # > total_units
        ]
        result = verifier.verify_no_overcharge(records, total_units=100)
        assert result["overcharged"]
        assert result["excess"] == 1

    def test_no_overcharge(self):
        from voucher.verifier import VoucherChainVerifier, UsageRecord
        verifier = VoucherChainVerifier()
        records = [
            UsageRecord("v1", 1, 1, 0, 1000),
        ]
        result = verifier.verify_no_overcharge(records, total_units=100)
        assert not result["overcharged"]


# ── SQLite 持久化 ────────────────────────────────────────

class TestSqliteVoucherStore:
    @pytest.fixture
    def store(self, tmp_path):
        from data.sqlite_store import SqliteVoucherStore
        return SqliteVoucherStore(str(tmp_path / "test_voucher.db"))

    def test_save_and_get(self, store):
        from voucher.models import Voucher
        from voucher.state import VoucherState
        v = Voucher(
            voucher_id="vch-store-1",
            issuer_wallet="0xBuyer",
            agent_id="agent-1",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
        )
        store.save(v)
        got = store.get("vch-store-1")
        assert got is not None
        assert got.voucher_id == "vch-store-1"
        assert got.state == VoucherState.ISSUED

    def test_update_units_used(self, store):
        from voucher.models import Voucher
        from voucher.state import VoucherState, VoucherStateMachine
        v = Voucher(
            voucher_id="vch-store-2",
            issuer_wallet="0xBuyer",
            agent_id="agent-1",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=100,
            total_deposit=Decimal("1.0"),
        )
        sm = VoucherStateMachine()
        sm.transition("activate")
        v.state = sm.state
        v.activated_at = int(time.time())
        v.units_used = 50
        store.save(v)

        got = store.get("vch-store-2")
        assert got.units_used == 50
        assert got.units_remaining == 50

    def test_get_by_agent(self, store):
        from voucher.models import Voucher
        for i in range(3):
            v = Voucher(
                voucher_id=f"vch-agent-{i}",
                issuer_wallet="0xBuyer",
                agent_id="agent-x",
                capability_task_type="data_delivery",
                unit_price=Decimal("0.01"),
                unit_type="api_call",
                total_units=10,
                total_deposit=Decimal("0.1"),
            )
            store.save(v)
        results = store.get_by_agent("agent-x")
        assert len(results) == 3

    def test_get_by_state(self, store):
        from voucher.models import Voucher
        from voucher.state import VoucherState
        v = Voucher(
            voucher_id="vch-issued",
            issuer_wallet="0xBuyer",
            agent_id="agent-1",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=10,
            total_deposit=Decimal("0.1"),
        )
        store.save(v)
        results = store.get_by_state(VoucherState.ISSUED)
        assert len(results) >= 1

    def test_count(self, store):
        from voucher.models import Voucher
        assert store.count() == 0
        v = Voucher(
            voucher_id="vch-cnt",
            issuer_wallet="0xBuyer",
            agent_id="agent-1",
            capability_task_type="data_delivery",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
            total_units=10,
            total_deposit=Decimal("0.1"),
        )
        store.save(v)
        assert store.count() == 1


# ── CapabilitySpec metered pricing ────────────────────────

class TestMeteredPricing:
    def test_capability_spec_metered(self):
        from agent.capability import CapabilitySpec
        spec = CapabilitySpec(
            task_type="data_delivery",
            verification_gate="data_delivery",
            pricing_model="metered",
            unit_price=Decimal("0.01"),
            unit_type="api_call",
        )
        d = spec.to_dict()
        assert d["pricing_model"] == "metered"
        assert d["unit_price"] == "0.01"
        assert d["unit_type"] == "api_call"

    def test_capability_spec_from_dict_metered(self):
        from agent.capability import CapabilitySpec
        data = {
            "task_type": "data_delivery",
            "verification_gate": "data_delivery",
            "pricing_model": "metered",
            "unit_price": "0.01",
            "unit_type": "api_call",
        }
        spec = CapabilitySpec.from_dict(data)
        assert spec.pricing_model == "metered"
        assert spec.unit_price == Decimal("0.01")
        assert spec.unit_type == "api_call"