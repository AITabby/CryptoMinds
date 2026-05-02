"""Extended tests for market_listener — start/stop lifecycle,
_run_loop polling, _handle_task edge cases, submit_task detail,
TaskMatcher additional cases, create_listener_for_daemon."""
import json
import time
import threading
from unittest.mock import patch, MagicMock, call
from decimal import Decimal
import pytest

from market_listener import MarketListener, MarketTask, TaskMatcher, create_listener_for_daemon


def _make_task(task_id="t1", task_type="token_delivery", amount=Decimal("0.01"),
               chain="bsc", channel_id="bsc-native"):
    return MarketTask(
        task_id=task_id, task_type=task_type, buyer_wallet="0xbuyer",
        amount=amount, chain=chain, channel_id=channel_id,
    )


# ── MarketListener start / stop lifecycle ────────────────────────────────────

class TestStartStopLifecycle:

    def test_start_creates_thread(self):
        listener = MarketListener(market_url="http://fake", poll_interval=1.0)
        with patch.object(listener, "_fetch_tasks", return_value=[]):
            listener.start()
            assert listener._running is True
            assert listener._thread is not None
            assert listener._thread.daemon is True
            # Let it run one cycle then stop
            time.sleep(1.5)
            listener.stop()
            assert listener._running is False

    def test_start_no_double_start(self):
        listener = MarketListener(market_url="http://fake", poll_interval=1.0)
        with patch.object(listener, "_fetch_tasks", return_value=[]):
            listener.start()
            first_thread = listener._thread
            # Second start should be no-op
            listener.start()
            assert listener._thread is first_thread
            time.sleep(1.5)
            listener.stop()

    def test_stop_sets_running_false(self):
        listener = MarketListener(market_url="http://fake", poll_interval=0.5)
        with patch.object(listener, "_fetch_tasks", return_value=[]):
            listener.start()
            time.sleep(1.0)
            listener.stop()
            assert listener._running is False

    def test_stop_without_start_is_safe(self):
        listener = MarketListener(market_url="http://fake")
        listener.stop()  # should not crash
        assert listener._running is False


# ── _run_loop polling ───────────────────────────────────────────────────────

class TestRunLoop:

    def test_run_loop_processes_new_task(self):
        listener = MarketListener(market_url="http://fake", poll_interval=0.3)
        task = _make_task()
        received_tasks = []

        def callback(t):
            received_tasks.append(t)
            return True

        listener.on_task(callback)

        with patch.object(listener, "_fetch_tasks", return_value=[task]):
            listener.start()
            time.sleep(0.8)
            listener.stop()

        assert len(received_tasks) >= 1
        assert received_tasks[0].task_id == "t1"

    def test_run_loop_skips_already_processed_task(self):
        listener = MarketListener(market_url="http://fake", poll_interval=0.3)
        task = _make_task(task_id="dup")
        call_count = []

        listener.on_task(lambda t: (call_count.append(1), True)[1])

        with patch.object(listener, "_fetch_tasks", return_value=[task]):
            listener.start()
            time.sleep(0.8)
            # First cycle should process it
            first_count = len(call_count)
            time.sleep(0.8)
            # Second cycle should skip it (already processed)
            second_count = len(call_count)
            listener.stop()

        assert first_count >= 1
        assert second_count == first_count  # no additional calls

    def test_run_loop_cleans_processed_set_when_large(self):
        listener = MarketListener(market_url="http://fake", poll_interval=0.3)
        # Pre-fill processed set to trigger cleanup
        for i in range(10001):
            listener._processed_tasks.add(f"old_{i}")

        with patch.object(listener, "_fetch_tasks", return_value=[]):
            listener.start()
            time.sleep(0.6)
            listener.stop()

        # After cleanup, set should be <= 5000
        assert len(listener._processed_tasks) <= 5001

    def test_run_loop_exception_does_not_crash(self):
        listener = MarketListener(market_url="http://fake", poll_interval=0.3)

        call_count = [0]
        def failing_fetch():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")
            return []

        with patch.object(listener, "_fetch_tasks", side_effect=failing_fetch):
            listener.start()
            time.sleep(1.2)
            listener.stop()

        # Should have survived the exception and continued polling
        assert call_count[0] >= 2


# ── _handle_task edge cases ─────────────────────────────────────────────────

class TestHandleTaskExtended:

    def test_callback_returns_false_continues_to_next(self):
        listener = MarketListener(market_url="http://fake")
        accepted_by = []
        listener.on_task(lambda t: (accepted_by.append("first"), False)[1])
        listener.on_task(lambda t: (accepted_by.append("second"), True)[1])
        listener._handle_task(_make_task())
        assert "first" in accepted_by
        assert "second" in accepted_by

    def test_no_callbacks_does_not_crash(self):
        listener = MarketListener(market_url="http://fake")
        listener._handle_task(_make_task())  # no callbacks registered


# ── submit_task extended ────────────────────────────────────────────────────

class TestSubmitTaskExtended:

    def test_submit_posts_json_with_correct_fields(self):
        listener = MarketListener(market_url="http://fake")
        task = _make_task()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()

        captured_req = []
        def capture_urlopen(req, timeout=None):
            captured_req.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=capture_urlopen):
            result = listener.submit_task(task)

        assert result is True
        assert len(captured_req) == 1
        req = captured_req[0]
        # Verify it's a POST with JSON data
        assert req.data is not None
        posted = json.loads(req.data)
        assert posted["task_id"] == "t1"
        assert posted["task_type"] == "token_delivery"
        assert req.get_header("Content-type") == "application/json"

    def test_submit_returns_false_on_server_error(self):
        listener = MarketListener(market_url="http://fake")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "error": "rejected"}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = listener.submit_task(_make_task())

        assert result is False

    def test_submit_with_timeout_kwarg(self):
        listener = MarketListener(market_url="http://fake")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            listener.submit_task(_make_task())

        # Verify timeout=10 was passed
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        assert call_args[1].get("timeout") == 10


# ── TaskMatcher additional edge cases ────────────────────────────────────────

class TestTaskMatcherExtended:

    def test_match_empty_task_types_accepts_any(self):
        matcher = TaskMatcher(task_types=[])
        assert matcher.match(_make_task(task_type="anything")) is True

    def test_match_empty_chains_accepts_any(self):
        matcher = TaskMatcher(supported_chains=[])
        assert matcher.match(_make_task(chain="solana")) is True

    def test_match_amount_exactly_at_min(self):
        matcher = TaskMatcher(min_amount=Decimal("0.01"))
        # Exactly at min should pass (not < min)
        assert matcher.match(_make_task(amount=Decimal("0.01"))) is True

    def test_match_amount_exactly_at_max(self):
        matcher = TaskMatcher(max_amount=Decimal("0.1"))
        # Exactly at max should pass (not > max)
        assert matcher.match(_make_task(amount=Decimal("0.1"))) is True

    def test_match_no_min_max_accepts_any_amount(self):
        matcher = TaskMatcher(min_amount=None, max_amount=None)
        assert matcher.match(_make_task(amount=Decimal("999"))) is True

    def test_market_task_to_dict(self):
        task = MarketTask(
            task_id="t2", task_type="data_delivery",
            buyer_wallet="0xb2", amount=Decimal("0.5"),
            chain="eth", channel_id="eth-1",
            params={"key": "val"}, created_at=100, deadline=200,
        )
        d = task.to_dict()
        assert d["task_id"] == "t2"
        assert d["amount"] == "0.5"
        assert d["params"] == {"key": "val"}
        assert d["created_at"] == 100


# ── create_listener_for_daemon ──────────────────────────────────────────────

class TestCreateListenerForDaemon:

    def test_creates_listener_with_callback(self):
        # Mock agent_daemon module with Task class
        mock_task_cls = MagicMock()
        mock_daemon = MagicMock()
        mock_daemon.config.wallet = "0xSELLER"
        mock_daemon.submit_task.return_value = True

        with patch.dict("sys.modules", {"agent_daemon": MagicMock(Task=mock_task_cls)}):
            listener = create_listener_for_daemon(mock_daemon, market_url="http://fake")

        assert isinstance(listener, MarketListener)
        assert len(listener._callbacks) == 1

    def test_callback_creates_task_and_submits(self):
        mock_task_cls = MagicMock()
        mock_daemon = MagicMock()
        mock_daemon.config.wallet = "0xSELLER"
        mock_daemon.submit_task.return_value = True

        with patch.dict("sys.modules", {"agent_daemon": MagicMock(Task=mock_task_cls)}):
            listener = create_listener_for_daemon(mock_daemon, market_url="http://fake")

        # Invoke the registered callback
        market_task = _make_task()
        callback = listener._callbacks[0]
        result = callback(market_task)

        assert result is True
        mock_daemon.submit_task.assert_called_once()

    def test_callback_returns_false_on_rejection(self):
        mock_task_cls = MagicMock()
        mock_daemon = MagicMock()
        mock_daemon.config.wallet = "0xSELLER"
        mock_daemon.submit_task.return_value = False

        with patch.dict("sys.modules", {"agent_daemon": MagicMock(Task=mock_task_cls)}):
            listener = create_listener_for_daemon(mock_daemon, market_url="http://fake")

        callback = listener._callbacks[0]
        result = callback(_make_task())

        assert result is False

    def test_custom_market_url_propagated(self):
        mock_daemon = MagicMock()
        mock_daemon.config.wallet = "0xSELLER"

        with patch.dict("sys.modules", {"agent_daemon": MagicMock(Task=MagicMock())}):
            listener = create_listener_for_daemon(mock_daemon, market_url="http://custom:9999")

        assert listener.market_url == "http://custom:9999"