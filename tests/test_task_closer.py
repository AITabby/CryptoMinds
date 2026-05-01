"""Tests for TaskCloser and EscrowManager — close_task, escrow lifecycle."""
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from task_closer import TaskCloser, EscrowManager, TaskResult
from verification.base import TaskOutput, VerificationResult
from settlement.base import PaymentResult


def _mock_verify_success():
    return VerificationResult(success=True, gate_id="token_delivery",
                              task_type="token_delivery", score=0.95,
                              evidence={"tx_hash": "0xabc"})


def _mock_verify_failure():
    return VerificationResult(success=False, gate_id="token_delivery",
                              task_type="token_delivery", error="bad output")


@pytest.fixture(autouse=True)
def _clear_globals():
    """Reset global instances to avoid cross-test leakage."""
    from task_closer import task_closer, escrow_manager
    escrow_manager._escrows.clear()
    yield
    escrow_manager._escrows.clear()


class TestCloseTask:

    def test_verify_failure_returns_failed(self):
        closer = TaskCloser()
        output = TaskOutput(task_type="token_delivery", seller_wallet="0xs",
                            tx_hash="0xabc", token_address="0xt", token_amount="1")
        with patch("task_closer.verify_task", return_value=_mock_verify_failure()), \
             patch("task_closer.record_task_completion"):
            result = closer.close_task(
                "t1", "token_delivery", "0xb", "0xs", "agent-1",
                "bsc", Decimal("0.01"), "mock", output,
            )
        assert result.verified is False
        assert result.success is False

    def test_verify_pass_settle_pass_records_settled(self):
        closer = TaskCloser()
        output = TaskOutput(task_type="token_delivery", seller_wallet="0xs",
                            tx_hash="0xabc", token_address="0xt", token_amount="1")
        with patch("task_closer.verify_task", return_value=_mock_verify_success()), \
             patch("task_closer.record_task_completion") as mock_record, \
             patch("task_closer.update_agent_reputation"), \
             patch("task_closer.ChannelRegistry.get") as mock_channel:
            mock_channel_obj = MagicMock()
            mock_channel_obj.escrow_release.return_value = PaymentResult(
                success=True, channel_id="mock", order_id="t1", tx_hash="0xrelease")
            mock_channel.return_value = mock_channel_obj

            result = closer.close_task(
                "t1", "token_delivery", "0xb", "0xs", "agent-1",
                "bsc", Decimal("0.01"), "mock", output,
                escrow_id="esc-1", private_key="0xkey",
            )
        assert result.verified is True
        assert result.paid is True
        assert result.success is True

    def test_no_escrow_direct_payment(self):
        closer = TaskCloser()
        output = TaskOutput(task_type="token_delivery", seller_wallet="0xs",
                            tx_hash="0xabc", token_address="0xt", token_amount="1")
        with patch("task_closer.verify_task", return_value=_mock_verify_success()), \
             patch("task_closer.record_task_completion"), \
             patch("task_closer.update_agent_reputation"), \
             patch("task_closer.ChannelRegistry.get") as mock_channel:
            mock_channel_obj = MagicMock()
            mock_channel.return_value = mock_channel_obj

            result = closer.close_task(
                "t1", "token_delivery", "0xb", "0xs", "agent-1",
                "bsc", Decimal("0.01"), "mock", output,
            )
        assert result.paid is True
        assert result.tx_hash == "direct_payment"


class TestEscrowManager:

    def test_create_escrow_unknown_channel(self):
        with patch("task_closer.ChannelRegistry.get", return_value=None):
            result = EscrowManager().create_escrow(
                "0xb", "0xs", Decimal("0.01"), "unknown", "t1")
        assert "error" in result

    def test_create_escrow_channel_no_escrow_support(self):
        mock_channel = MagicMock()
        mock_channel.supports_escrow = False
        with patch("task_closer.ChannelRegistry.get", return_value=mock_channel):
            result = EscrowManager().create_escrow(
                "0xb", "0xs", Decimal("0.01"), "mock", "t1")
        assert "不支持托管" in result["error"]

    def test_create_escrow_success(self):
        mock_channel = MagicMock()
        mock_channel.supports_escrow = True
        mock_channel.escrow_lock.return_value = MagicMock(success=True, escrow_id="esc-1")
        mgr = EscrowManager()
        with patch("task_closer.ChannelRegistry.get", return_value=mock_channel):
            result = mgr.create_escrow("0xb", "0xs", Decimal("0.01"), "mock", "t1")
        assert result["ok"] is True
        assert result["escrow_id"] == "esc-1"

    def test_get_escrow_found(self):
        mgr = EscrowManager()
        mgr._escrows["e1"] = {"escrow_id": "e1", "status": "locked"}
        assert mgr.get_escrow("e1") is not None

    def test_get_escrow_not_found(self):
        assert EscrowManager().get_escrow("none") is None

    def test_release_escrow_success(self):
        mock_channel = MagicMock()
        mock_channel.escrow_release.return_value = PaymentResult(
            success=True, tx_hash="0xrelease")
        mgr = EscrowManager()
        mgr._escrows["e1"] = {"status": "locked"}
        with patch("task_closer.ChannelRegistry.get", return_value=mock_channel):
            result = mgr.release_escrow("e1", "0xs", "mock", "0xkey")
        assert result["success"] is True
        assert mgr._escrows["e1"]["status"] == "released"

    def test_refund_escrow_success(self):
        mock_channel = MagicMock()
        mock_channel.escrow_refund.return_value = PaymentResult(
            success=True, tx_hash="0xrefund")
        mgr = EscrowManager()
        mgr._escrows["e1"] = {"status": "locked"}
        with patch("task_closer.ChannelRegistry.get", return_value=mock_channel):
            result = mgr.refund_escrow("e1", "0xb", "mock", "0xkey")
        assert result["success"] is True
        assert mgr._escrows["e1"]["status"] == "refunded"