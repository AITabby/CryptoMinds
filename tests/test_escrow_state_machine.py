"""Tests for Escrow state machine, dispute resolution, and arbitration."""

import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError, VALID_TRANSITIONS
from escrow.models import EscrowOrder
from escrow.arbitration import ArbitrationEngine


class TestEscrowState:
    def test_state_values(self):
        assert EscrowState.CREATED.value == "created"
        assert EscrowState.FUNDED.value == "funded"
        assert EscrowState.DISPUTED.value == "disputed"
        assert EscrowState.RELEASED.value == "released"

    def test_from_chain_status(self):
        assert EscrowState.from_chain_status(0) == EscrowState.CREATED
        assert EscrowState.from_chain_status(1) == EscrowState.FUNDED
        assert EscrowState.from_chain_status(5) == EscrowState.DISPUTED

    def test_to_chain_status(self):
        assert EscrowState.FUNDED.to_chain_status() == 1
        assert EscrowState.DISPUTED.to_chain_status() == 5

    def test_is_terminal(self):
        assert EscrowState.RELEASED.is_terminal
        assert EscrowState.RESOLVED_REFUND.is_terminal
        assert EscrowState.EXPIRED.is_terminal
        assert not EscrowState.CREATED.is_terminal
        assert not EscrowState.DELIVERED.is_terminal


class TestEscrowStateMachine:
    def test_initial_state(self):
        sm = EscrowStateMachine()
        assert sm.state == EscrowState.CREATED

    def test_valid_transition_fund(self):
        sm = EscrowStateMachine()
        new = sm.transition("fund", timestamp=100, actor="buyer")
        assert new == EscrowState.FUNDED
        assert sm.state == EscrowState.FUNDED

    def test_valid_full_path(self):
        sm = EscrowStateMachine()
        sm.transition("fund", timestamp=1)
        sm.transition("seller_accept", timestamp=2)
        sm.transition("deliver", timestamp=3)
        sm.transition("verify_pass", timestamp=4)
        sm.transition("release", timestamp=5)
        assert sm.state == EscrowState.RELEASED

    def test_invalid_transition_raises(self):
        sm = EscrowStateMachine(EscrowState.CREATED)
        with pytest.raises(InvalidTransitionError):
            sm.transition("deliver")

    def test_can_transition(self):
        sm = EscrowStateMachine(EscrowState.CREATED)
        assert sm.can_transition("fund")
        assert not sm.can_transition("deliver")

    def test_dispute_from_delivered_verify_fail(self):
        sm = EscrowStateMachine(EscrowState.DELIVERED)
        new = sm.transition("verify_fail", timestamp=100)
        assert new == EscrowState.DISPUTED

    def test_dispute_from_delivered_low_score(self):
        sm = EscrowStateMachine(EscrowState.DELIVERED)
        new = sm.transition("verify_low_score", timestamp=100)
        assert new == EscrowState.DISPUTED

    def test_arbitrate_buyer_win(self):
        sm = EscrowStateMachine(EscrowState.DISPUTED)
        new = sm.transition("arbitrate_buyer_win", timestamp=100)
        assert new == EscrowState.RESOLVED_REFUND

    def test_arbitrate_seller_win(self):
        sm = EscrowStateMachine(EscrowState.DISPUTED)
        new = sm.transition("arbitrate_seller_win", timestamp=100)
        assert new == EscrowState.RESOLVED_RELEASE

    def test_auto_resolve_seller_win(self):
        sm = EscrowStateMachine(EscrowState.DISPUTED)
        new = sm.transition("auto_resolve_seller_win", timestamp=100)
        assert new == EscrowState.RESOLVED_RELEASE

    def test_auto_resolve_buyer_win(self):
        sm = EscrowStateMachine(EscrowState.DISPUTED)
        new = sm.transition("auto_resolve_buyer_win", timestamp=100)
        assert new == EscrowState.RESOLVED_REFUND

    def test_seller_timeout_from_funded(self):
        sm = EscrowStateMachine(EscrowState.FUNDED)
        new = sm.transition("seller_timeout", timestamp=100)
        assert new == EscrowState.REFUNDED_TIMEOUT

    def test_buyer_timeout_from_delivered(self):
        sm = EscrowStateMachine(EscrowState.DELIVERED)
        new = sm.transition("buyer_timeout", timestamp=100)
        assert new == EscrowState.EXPIRED

    def test_history_records_transitions(self):
        sm = EscrowStateMachine()
        sm.transition("fund", timestamp=1, actor="buyer")
        sm.transition("seller_accept", timestamp=2, actor="seller")
        assert len(sm.history) == 2
        assert sm.history[0].action == "fund"
        assert sm.history[1].from_state == EscrowState.FUNDED

    def test_no_transition_from_terminal(self):
        sm = EscrowStateMachine(EscrowState.RELEASED)
        assert not sm.can_transition("fund")
        with pytest.raises(InvalidTransitionError):
            sm.transition("fund")

    def test_dispute_from_delivered_manual(self):
        sm = EscrowStateMachine(EscrowState.DELIVERED)
        new = sm.transition("dispute", timestamp=100, actor="buyer", reason="不满意")
        assert new == EscrowState.DISPUTED


class TestEscrowOrder:
    def test_create_order(self):
        order = EscrowOrder(
            escrow_id="esc-001",
            task_id="task-001",
            order_id="ord-001",
            buyer_wallet="0xBUYER",
            seller_wallet="0xSELLER",
            seller_agent_id="agent-001",
            amount=Decimal("0.5"),
            channel_id="bsc-native",
        )
        assert order.state == EscrowState.CREATED
        assert order.verification_threshold == 0.7

    def test_to_dict(self):
        order = EscrowOrder(
            escrow_id="esc-001", task_id="t1", order_id="o1",
            buyer_wallet="0xB", seller_wallet="0xS", seller_agent_id="a1",
            amount=Decimal("1.0"), channel_id="mock",
        )
        d = order.to_dict()
        assert d["state"] == "created"
        assert d["amount"] == "1.0"
        assert d["dispute_window_seconds"] == 172800


class TestArbitrationEngine:
    def _make_engine(self):
        escrow_store = MagicMock()
        record_store = MagicMock()
        agent_registry = MagicMock()

        def get_order(escrow_id):
            order = EscrowOrder(
                escrow_id=escrow_id, task_id="t1", order_id="o1",
                buyer_wallet="0xB", seller_wallet="0xS", seller_agent_id="agent-1",
                amount=Decimal("1.0"), channel_id="mock",
                state=EscrowState.DISPUTED,
                disputed_at=int(time.time()) - 200000,
                arbitration_weight_buyer=0.3,
                arbitration_weight_seller=0.7,
            )
            return order

        escrow_store.get = get_order
        escrow_store.save = MagicMock()

        agent = MagicMock()
        agent.reputation.score = 3.5
        agent.wallet = "0xS"
        agent.staked = Decimal("2.0")
        agent.online = True
        agent_registry.get = MagicMock(return_value=agent)
        agent_registry.update = MagicMock()

        record_store.get_by_seller = MagicMock(return_value=[])

        return ArbitrationEngine(escrow_store, record_store, agent_registry), escrow_store

    def test_resolve_buyer_win(self):
        engine, store = self._make_engine()
        result = engine.resolve_dispute("esc-001", "0xADMIN", "buyer_win", "卖家未交付")
        assert result["ok"]
        assert result["resolution"] == "buyer_win"

    def test_resolve_seller_win(self):
        engine, store = self._make_engine()
        result = engine.resolve_dispute("esc-001", "0xADMIN", "seller_win", "买家恶意争议")
        assert result["ok"]
        assert result["resolution"] == "seller_win"

    def test_resolve_split(self):
        engine, store = self._make_engine()
        result = engine.resolve_dispute("esc-001", "0xADMIN", "split", "部分完成")
        assert result["ok"]
        assert result["resolution"] == "split"

    def test_invalid_decision(self):
        engine, store = self._make_engine()
        result = engine.resolve_dispute("esc-001", "0xADMIN", "invalid")
        assert "error" in result

    def test_auto_resolve_timeout_seller_higher_rep(self):
        engine, store = self._make_engine()
        result = engine.auto_resolve_timeout("esc-001")
        assert result["ok"]
        assert result["resolution"] == "seller_win"

    def test_auto_resolve_timeout_buyer_higher_rep(self):
        engine, store = self._make_engine()
        order = store.get("esc-001")
        order.arbitration_weight_buyer = 0.8
        order.arbitration_weight_seller = 0.2
        # Override store.get to return modified order
        store.get = MagicMock(return_value=order)
        result = engine.auto_resolve_timeout("esc-001")
        assert result["ok"]
        assert result["resolution"] == "buyer_win"

    def test_auto_resolve_not_yet_expired(self):
        engine, store = self._make_engine()
        order = store.get("esc-001")
        order.disputed_at = int(time.time())  # just now
        order.dispute_window_seconds = 172800
        # Override store.get to return modified order
        store.get = MagicMock(return_value=order)
        result = engine.auto_resolve_timeout("esc-001")
        assert "error" in result

    def test_calculate_arbitration_weights(self):
        engine, store = self._make_engine()
        buyer_w, seller_w = engine.calculate_arbitration_weights("0xB", "agent-1")
        assert seller_w > buyer_w  # seller has higher rep

    def test_slash_seller_first_dispute(self):
        engine, store = self._make_engine()
        agent = engine._agent_registry.get("agent-1")
        original_score = agent.reputation.score

        # Mock: 1 buyer_win dispute
        record = MagicMock()
        record.disputed = True
        record.resolution = "buyer_win"
        engine._record_store.get_by_seller = MagicMock(return_value=[record])

        engine._slash_seller("agent-1")
        assert agent.reputation.score == original_score - 0.3

    def test_slash_seller_repeated_failure(self):
        engine, store = self._make_engine()
        agent = engine._agent_registry.get("agent-1")
        agent.staked = Decimal("2.0")

        # Mock: 3 buyer_win disputes
        records = [MagicMock(disputed=True, resolution="buyer_win") for _ in range(3)]
        engine._record_store.get_by_seller = MagicMock(return_value=records)

        engine._slash_seller("agent-1")
        assert agent.reputation.score == max(0, 3.5 - 1.0)
        assert agent.staked == Decimal("1.0")  # 50% slash

    def test_slash_seller_ban(self):
        engine, store = self._make_engine()
        agent = engine._agent_registry.get("agent-1")

        # Mock: 5+ buyer_win disputes
        records = [MagicMock(disputed=True, resolution="buyer_win") for _ in range(6)]
        engine._record_store.get_by_seller = MagicMock(return_value=records)

        engine._slash_seller("agent-1")
        assert agent.reputation.score == 0.0
        assert agent.online == False