"""Tests for MarketListener and TaskMatcher — fetch, match, callbacks."""
import json
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from market_listener import MarketListener, MarketTask, TaskMatcher


def _make_task(task_id="t1", task_type="token_delivery", amount=Decimal("0.01"),
               chain="bsc", channel_id="bsc-native"):
    return MarketTask(
        task_id=task_id, task_type=task_type, buyer_wallet="0xbuyer",
        amount=amount, chain=chain, channel_id=channel_id,
    )


class TestTaskMatcher:

    def test_match_by_type(self):
        matcher = TaskMatcher(task_types=["token_delivery"])
        assert matcher.match(_make_task(task_type="token_delivery")) is True
        assert matcher.match(_make_task(task_type="data_delivery")) is False

    def test_match_by_chain(self):
        matcher = TaskMatcher(supported_chains=["bsc"])
        assert matcher.match(_make_task(chain="bsc")) is True
        assert matcher.match(_make_task(chain="eth")) is False

    def test_match_by_min_amount(self):
        matcher = TaskMatcher(min_amount=Decimal("0.01"))
        assert matcher.match(_make_task(amount=Decimal("0.02"))) is True
        assert matcher.match(_make_task(amount=Decimal("0.005"))) is False

    def test_match_by_max_amount(self):
        matcher = TaskMatcher(max_amount=Decimal("0.1"))
        assert matcher.match(_make_task(amount=Decimal("0.05"))) is True
        assert matcher.match(_make_task(amount=Decimal("0.2"))) is False

    def test_empty_filters_match_all(self):
        matcher = TaskMatcher()
        assert matcher.match(_make_task()) is True

    def test_combined_filters(self):
        matcher = TaskMatcher(task_types=["token_delivery"], supported_chains=["bsc"])
        task = _make_task(task_type="token_delivery", chain="bsc")
        assert matcher.match(task) is True


class TestFetchTasks:

    def test_fetch_returns_tasks(self):
        listener = MarketListener(market_url="http://fake")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "tasks": [{"task_id": "t1", "task_type": "token_delivery",
                       "buyer_wallet": "0xb", "amount": "0.01",
                       "chain": "bsc", "channel_id": "bsc-native"}]
        }).encode()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tasks = listener._fetch_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"

    def test_fetch_url_error_returns_empty(self):
        listener = MarketListener(market_url="http://fake")
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            tasks = listener._fetch_tasks()
        assert tasks == []

    def test_fetch_malformed_json_returns_empty(self):
        listener = MarketListener(market_url="http://fake")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        with patch("urllib.request.urlopen", return_value=mock_resp):
            tasks = listener._fetch_tasks()
        assert tasks == []


class TestHandleTask:

    def test_callback_receives_task(self):
        listener = MarketListener(market_url="http://fake")
        received = []
        listener.on_task(lambda t: (received.append(t), True)[1])
        task = _make_task()
        listener._handle_task(task)
        assert len(received) == 1
        assert received[0].task_id == "t1"

    def test_callback_returning_true_stops_further(self):
        listener = MarketListener(market_url="http://fake")
        calls = []
        listener.on_task(lambda t: (calls.append("first"), True)[1])
        listener.on_task(lambda t: (calls.append("second"), True)[1])
        listener._handle_task(_make_task())
        assert calls == ["first"]

    def test_callback_exception_caught(self):
        listener = MarketListener(market_url="http://fake")
        listener.on_task(lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
        listener.on_task(lambda t: True)
        # Should not crash, second callback still runs
        listener._handle_task(_make_task())


class TestSubmitTask:

    def test_submit_success(self):
        listener = MarketListener(market_url="http://fake")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert listener.submit_task(_make_task()) is True

    def test_submit_failure(self):
        listener = MarketListener(market_url="http://fake")
        with patch("urllib.request.urlopen", side_effect=Exception("fail")):
            assert listener.submit_task(_make_task()) is False