"""Tests for EscrowWatchdog — timeout enforcement for escrow orders."""
import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_store():
    """Create a mock escrow store with get_by_state and save methods."""
    store = MagicMock()
    store.get_by_state.return_value = []
    store.save = MagicMock()
    store.get = MagicMock(return_value=None)
    return store


class TestEscrowWatchdogSellerTimeout:

    def test_seller_timeout_funded(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-1"
        order.state = EscrowState.FUNDED
        order.seller_timeout_at = int(time.time()) - 100  # already expired
        order.buyer_timeout_at = 0

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.FUNDED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-1" in triggered

    def test_seller_timeout_executing(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-2"
        order.state = EscrowState.EXECUTING
        order.seller_timeout_at = int(time.time()) - 50
        order.buyer_timeout_at = 0

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.EXECUTING else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-2" in triggered

    def test_seller_not_yet_timed_out(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-3"
        order.state = EscrowState.FUNDED
        order.seller_timeout_at = int(time.time()) + 3600  # 1 hour from now
        order.buyer_timeout_at = 0

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.FUNDED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-3" not in triggered

    def test_seller_timeout_zero_not_triggered(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-4"
        order.state = EscrowState.FUNDED
        order.seller_timeout_at = 0  # never set
        order.buyer_timeout_at = 0

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.FUNDED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-4" not in triggered


class TestEscrowWatchdogBuyerTimeout:

    def test_buyer_timeout_delivered(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-5"
        order.state = EscrowState.DELIVERED
        order.seller_timeout_at = 0
        order.buyer_timeout_at = int(time.time()) - 100

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.DELIVERED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-5" in triggered

    def test_buyer_not_yet_timed_out(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-test-6"
        order.state = EscrowState.DELIVERED
        order.seller_timeout_at = 0
        order.buyer_timeout_at = int(time.time()) + 86400

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.DELIVERED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert "esc-test-6" not in triggered


class TestEscrowWatchdogTrigger:

    def test_trigger_seller_timeout_state_transition(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-trigger-1"
        order.state = EscrowState.FUNDED
        order.seller_timeout_at = int(time.time()) - 10
        order.buyer_timeout_at = 0
        order.channel_id = "mock"
        order.on_chain_order_id = ""

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.FUNDED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        wd._trigger_seller_timeout(order)

        assert order.state == EscrowState.REFUNDED_TIMEOUT
        mock_store.save.assert_called_once_with(order)

    def test_trigger_buyer_timeout_state_transition(self, mock_store):
        from settlement.escrow_state import EscrowState
        from escrow.watchdog import EscrowWatchdog

        order = MagicMock()
        order.escrow_id = "esc-trigger-2"
        order.state = EscrowState.DELIVERED
        order.seller_timeout_at = 0
        order.buyer_timeout_at = int(time.time()) - 10
        order.channel_id = "mock"
        order.on_chain_order_id = ""

        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.DELIVERED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        wd._trigger_buyer_timeout(order)

        assert order.state == EscrowState.EXPIRED
        mock_store.save.assert_called_once_with(order)


class TestEscrowWatchdogLifecycle:

    def test_start_stop(self, mock_store):
        from escrow.watchdog import EscrowWatchdog
        wd = EscrowWatchdog(mock_store, check_interval=300)
        wd.start()
        assert wd._running is True
        assert wd._thread is not None
        wd.stop()
        assert wd._running is False

    def test_double_start(self, mock_store):
        from escrow.watchdog import EscrowWatchdog
        wd = EscrowWatchdog(mock_store, check_interval=300)
        wd.start()
        thread1 = wd._thread
        wd.start()  # should be no-op
        assert wd._thread is thread1
        wd.stop()

    def test_no_timeouts_empty_store(self, mock_store):
        from escrow.watchdog import EscrowWatchdog
        mock_store.get_by_state.return_value = []
        wd = EscrowWatchdog(mock_store, check_interval=300)
        triggered = wd.check_once()
        assert triggered == []


class TestEscrowWatchdogDisputeTimeout:

    def test_chain_dispute_timeout_keeps_state_when_chain_fails(self, mock_store):
        from decimal import Decimal
        from escrow.models import EscrowOrder
        from escrow.watchdog import EscrowWatchdog
        from settlement.escrow_state import EscrowState

        order = EscrowOrder(
            escrow_id="esc-dispute-1",
            task_id="task-1",
            order_id="order-1",
            buyer_wallet="0xBuyer",
            seller_wallet="0xSeller",
            seller_agent_id="seller-1",
            amount=Decimal("1"),
            channel_id="bsc-native",
            state=EscrowState.DISPUTED,
            disputed_at=int(time.time()) - 100,
            dispute_window_seconds=1,
            on_chain_order_id="0x" + "11" * 32,
            arbitration_weight_buyer=1.0,
            arbitration_weight_seller=0.0,
        )
        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.DISPUTED else []

        wd = EscrowWatchdog(mock_store, MagicMock(), MagicMock(), check_interval=300)
        with patch.object(wd, "_try_chain_arbitration", return_value=False):
            wd._check_dispute_timeouts()

        assert order.state == EscrowState.DISPUTED
        assert order.chain_synced is False
        mock_store.save.assert_called_with(order)

    def test_dispute_timeout_without_dependencies_keeps_disputed(self, mock_store):
        from decimal import Decimal
        from escrow.models import EscrowOrder
        from escrow.watchdog import EscrowWatchdog
        from settlement.escrow_state import EscrowState

        order = EscrowOrder(
            escrow_id="esc-dispute-2",
            task_id="task-2",
            order_id="order-2",
            buyer_wallet="0xBuyer",
            seller_wallet="0xSeller",
            seller_agent_id="seller-2",
            amount=Decimal("1"),
            channel_id="mock",
            state=EscrowState.DISPUTED,
            disputed_at=int(time.time()) - 100,
            dispute_window_seconds=1,
        )
        mock_store.get_by_state.side_effect = lambda s: [order] if s == EscrowState.DISPUTED else []

        wd = EscrowWatchdog(mock_store, check_interval=300)
        wd._check_dispute_timeouts()

        assert order.state == EscrowState.DISPUTED
