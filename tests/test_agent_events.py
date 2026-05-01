"""Tests for agent_events — push, disabled mode, payload format."""
from unittest.mock import patch, MagicMock
import pytest


class TestDisabledMode:

    def test_disabled_skips_http(self):
        import agent_events
        original = agent_events.DISABLED
        agent_events.DISABLED = True
        with patch("requests.post") as mock_post:
            agent_events._push("think", "Agent1", "thinking...")
            mock_post.assert_not_called()
        agent_events.DISABLED = original

    def test_enabled_calls_http(self):
        import agent_events
        original = agent_events.DISABLED
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events._push("think", "Agent1", "thinking...")
            mock_post.assert_called_once()
        agent_events.DISABLED = original


class TestPayloadFormat:

    def test_think_payload(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events.think("Buyer", "searching sellers")
            call_kwargs = mock_post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["type"] == "think"
            assert payload["agent"] == "Buyer"
            assert payload["message"] == "searching sellers"
            assert "timestamp" in payload

    def test_pay_payload(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events.pay("Buyer", "Seller", 0.01, "fee", tx_hash="0xabc")
            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "pay"
            assert payload["to"] == "Seller"
            assert payload["amount"] == 0.01
            assert payload["tx_hash"] == "0xabc"

    def test_execute_payload(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events.execute("Seller", "buying tokens")
            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "execute"

    def test_result_payload(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events.result("Seller", "tokens transferred")
            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "result"

    def test_error_payload(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post") as mock_post:
            agent_events.error("Seller", "transfer failed")
            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "error"


class TestHttpFailure:

    def test_http_error_silently_swallowed(self):
        import agent_events
        agent_events.DISABLED = False
        with patch("requests.post", side_effect=Exception("network down")):
            agent_events._push("think", "Agent", "msg")
            # Should not raise