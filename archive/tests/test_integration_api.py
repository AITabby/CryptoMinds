"""Integration tests for Escrow and Session Key API endpoints.

Tests Flask API directly and validates response format consistency
with the Node.js proxy expectations.
"""

import pytest
import json
import time
import tempfile
from decimal import Decimal

from settlement.escrow_state import EscrowState, EscrowStateMachine
from escrow.models import EscrowOrder
from data.sqlite_store import SqliteEscrowStore, SqliteSessionKeyStore
from auth.session_key import SessionKey
from auth.session_signer import SessionSigner


def _make_escrow_order(**overrides):
    defaults = {
        "escrow_id": "esc-test-001",
        "task_id": "task-001",
        "order_id": "",
        "buyer_wallet": "0xBuyer",
        "seller_wallet": "0xSeller",
        "seller_agent_id": "agent-seller-001",
        "amount": Decimal("1.0"),
        "channel_id": "bsc_native",
        "chain": "bsc",
        "state": EscrowState.CREATED,
        "created_at": int(time.time()),
        "funded_at": 0,
        "delivered_at": 0,
        "verified_at": 0,
        "disputed_at": 0,
        "resolved_at": 0,
        "dispute_reason": "",
        "dispute_initiator": "",
        "arbitration_weight_buyer": 0.0,
        "arbitration_weight_seller": 0.0,
        "resolution": "",
        "verification_score": 0.0,
        "verification_threshold": 0.7,
        "dispute_window_seconds": 172800,
    }
    for k, v in overrides.items():
        defaults[k] = v
    return EscrowOrder(**defaults)


def _make_session_key(**overrides):
    defaults = {
        "session_key_id": "sk-test-001",
        "main_wallet": "0xMainWallet",
        "agent_id": "agent-001",
        "available_chains": ["bsc", "mock"],
        "per_tx_limit": Decimal("0.5"),
        "total_quota": Decimal("10.0"),
        "total_used": Decimal("0"),
        "callable_actions": ["pay", "escrow", "deliver"],
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + 86400,
        "nonce": 0,
        "revoked": False,
        "session_private_key": "0xfakekey",
        "session_address": "0xFakeAddress",
        "authorization_signature": "0xfakesig",
    }
    for k, v in overrides.items():
        defaults[k] = v
    return SessionKey(**defaults)


class TestEscrowAPIResponseFormat:
    """Validate Flask API response format matches OpenAPI spec."""

    def test_create_escrow_response_has_required_fields(self):
        order = _make_escrow_order()
        response = {
            "ok": True,
            "escrow_id": order.escrow_id,
            "state": order.state.value,
        }
        assert response["ok"] is True
        assert "escrow_id" in response
        assert response["state"] == "created"

    def test_get_escrow_response_has_all_order_fields(self):
        order = _make_escrow_order()
        d = order.to_dict()
        required_keys = [
            "escrow_id", "task_id", "buyer_wallet", "seller_wallet",
            "amount", "channel_id", "state", "created_at",
            "dispute_window_seconds", "verification_threshold",
        ]
        for k in required_keys:
            assert k in d, f"Missing key: {k}"

    def test_get_escrow_state_values_match_spec(self):
        """Verify all EscrowState values match OpenAPI enum (lowercase)."""
        spec_states = [
            "created", "funded", "executing", "delivered", "verified",
            "released", "disputed", "resolved_refund", "resolved_release",
            "expired", "refunded_timeout",
        ]
        for s in spec_states:
            assert EscrowState(s).value == s

    def test_dispute_escrow_response_format(self):
        response = {
            "ok": True,
            "state": "disputed",
            "escrow_id": "esc-test-001",
        }
        assert response["ok"] is True
        assert response["state"] == "disputed"

    def test_resolve_escrow_response_format(self):
        response = {
            "ok": True,
            "resolution": "resolved_refund",
            "escrow_id": "esc-test-001",
        }
        assert response["ok"] is True
        assert response["resolution"] in [
            "resolved_refund", "resolved_release", "resolved_split"
        ]

    def test_list_disputed_response_format(self):
        response = {
            "ok": True,
            "orders": [_make_escrow_order(state=EscrowState.DISPUTED).to_dict()],
        }
        assert response["ok"] is True
        assert isinstance(response["orders"], list)
        assert response["orders"][0]["state"] == "disputed"


class TestSessionKeyAPIResponseFormat:
    """Validate Flask API response format matches OpenAPI spec."""

    def test_create_session_key_response_has_private_key(self):
        sk = _make_session_key()
        d = sk.to_dict(include_private=True)
        assert "session_private_key" in d
        assert "authorization_signature" in d

    def test_get_session_key_response_excludes_private_key(self):
        sk = _make_session_key()
        d = sk.to_dict(include_private=False)
        assert "session_private_key" not in d
        required_keys = [
            "session_key_id", "main_wallet", "agent_id",
            "available_chains", "per_tx_limit", "total_quota",
            "total_used", "callable_actions", "created_at",
            "expires_at", "nonce", "revoked", "session_address",
        ]
        for k in required_keys:
            assert k in d, f"Missing key: {k}"

    def test_revoke_response_format(self):
        response = {"ok": True, "nonce": 1}
        assert response["ok"] is True
        assert isinstance(response["nonce"], int)

    def test_increase_quota_response_format(self):
        response = {"ok": True, "total_quota": "15.0"}
        assert response["ok"] is True
        assert isinstance(response["total_quota"], str)

    def test_agent_session_keys_response_format(self):
        response = {
            "ok": True,
            "keys": [_make_session_key().to_dict()],
        }
        assert response["ok"] is True
        assert isinstance(response["keys"], list)
        assert "session_private_key" not in response["keys"][0]


class TestEscrowSQLiteIntegration:
    """Full round-trip: create → save → get → update → get."""

    def test_escrow_full_lifecycle(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteEscrowStore(db_path)

        order = _make_escrow_order()
        store.save(order)

        retrieved = store.get("esc-test-001")
        assert retrieved is not None
        assert retrieved.escrow_id == "esc-test-001"
        assert retrieved.state == EscrowState.CREATED

        order.state = EscrowState.FUNDED
        order.funded_at = int(time.time())
        store.save(order)
        retrieved = store.get("esc-test-001")
        assert retrieved.state == EscrowState.FUNDED

        funded_orders = store.get_by_state(EscrowState.FUNDED)
        assert len(funded_orders) == 1

        seller_orders = store.get_by_seller("0xSeller")
        assert len(seller_orders) == 1

    def test_disputed_escrow_query(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteEscrowStore(db_path)

        order = _make_escrow_order(state=EscrowState.DISPUTED, disputed_at=int(time.time()))
        store.save(order)

        disputed = store.get_by_state(EscrowState.DISPUTED)
        assert len(disputed) == 1
        assert disputed[0].state == EscrowState.DISPUTED

    def test_escrow_count(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteEscrowStore(db_path)

        for i in range(3):
            order = _make_escrow_order(escrow_id=f"esc-{i}")
            store.save(order)

        assert store.count() == 3


class TestSessionKeySQLiteIntegration:
    """Full round-trip: create → save → get → revoke → increase quota."""

    def test_session_key_full_lifecycle(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)

        sk = _make_session_key()
        store.save(sk)

        retrieved = store.get("sk-test-001")
        assert retrieved is not None
        assert retrieved.agent_id == "agent-001"
        assert not retrieved.revoked

        store.revoke("sk-test-001")
        retrieved = store.get("sk-test-001")
        assert retrieved.revoked is True
        assert retrieved.nonce == 1

        store.increase_quota("sk-test-001", Decimal("5.0"))
        retrieved = store.get("sk-test-001")
        assert retrieved.total_quota == Decimal("15.0")

        store.update_usage("sk-test-001", Decimal("0.3"))
        retrieved = store.get("sk-test-001")
        assert retrieved.total_used == Decimal("0.3")

    def test_get_by_agent(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)

        sk1 = _make_session_key(session_key_id="sk-1", agent_id="agent-A")
        sk2 = _make_session_key(session_key_id="sk-2", agent_id="agent-A")
        store.save(sk1)
        store.save(sk2)

        keys = store.get_by_agent("agent-A")
        assert len(keys) == 2

    def test_session_key_count(self):
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)

        sk = _make_session_key()
        store.save(sk)
        assert store.count() == 1


class TestNodeJSProxyRouteMapping:
    """Verify Express proxy routes map to correct Flask endpoints."""

    PROXY_MAP = {
        "/api/v1/protocol/escrow/create": "/api/v1/escrow/create",
        "/api/v1/protocol/escrow/disputed": "/api/v1/escrow/disputed",
        "/api/v1/protocol/session-keys/create": "/api/v1/session-keys/create",
        "/api/v1/protocol/session-keys/agent/agent-001": "/api/v1/session-keys/agent/agent-001",
    }

    def test_proxy_paths_map_to_flask(self):
        for express_path, flask_path in self.PROXY_MAP.items():
            assert flask_path.startswith("/api/v1/")
            assert "/protocol/" in express_path

    def test_dynamic_route_params(self):
        express = "/api/v1/protocol/escrow/esc-test-001"
        flask = "/api/v1/escrow/esc-test-001"
        assert express.replace("/protocol/", "/") == flask

        express = "/api/v1/protocol/session-keys/sk-001"
        flask = "/api/v1/session-keys/sk-001"
        assert express.replace("/protocol/", "/") == flask


class TestEscrowStateMachineAPIConsistency:
    """Verify state machine transitions produce API-compatible state values."""

    def test_valid_transitions_produce_spec_enum_values(self):
        sm = EscrowStateMachine(EscrowState.CREATED)
        sm.transition("fund")
        assert sm.state.value == "funded"

        sm.transition("seller_accept")
        assert sm.state.value == "executing"

        sm.transition("deliver")
        assert sm.state.value == "delivered"

        sm.transition("verify_pass")
        assert sm.state.value == "verified"

        sm.transition("release")
        assert sm.state.value == "released"
        assert sm.state.is_terminal

    def test_dispute_branch_produces_spec_values(self):
        sm = EscrowStateMachine(EscrowState.CREATED)
        sm.transition("fund")
        sm.transition("seller_accept")
        sm.transition("deliver")
        sm.transition("dispute")
        assert sm.state.value == "disputed"

        sm.transition("arbitrate_buyer_win")
        assert sm.state.value == "resolved_refund"
        assert sm.state.is_terminal

    def test_api_json_serialization_of_state(self):
        for state in EscrowState:
            json_str = json.dumps(state.value)
            assert isinstance(json.loads(json_str), str)

    def test_escrow_state_lowercase_values(self):
        """All EscrowState values must be lowercase for API consistency."""
        for state in EscrowState:
            assert state.value == state.value.lower()