"""Tests for settlement/x402 — payment, escrow, wallet functions."""
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from settlement.registry import ChannelRegistry
from settlement.channels.mock import MockChannel
import settlement.x402 as x402_mod


MOCK_WALLETS = {
    "buyer": {"address": "0xBUYER", "private_key": "0xBKEY"},
    "seller": {"address": "0xSELLER", "private_key": "0xSKEY"},
}


@pytest.fixture(autouse=True)
def _setup_mock_channel():
    """Ensure mock channel is registered with a fresh balance."""
    if not ChannelRegistry.get("mock"):
        ChannelRegistry.register(MockChannel())
    mock_ch = ChannelRegistry.get("mock")
    mock_ch.set_balance("0xBUYER", Decimal("1.0"))
    yield


class TestInitDefaultChannels:

    def test_init_registers_channels(self):
        from settlement.x402 import init_default_channels
        init_default_channels()
        assert ChannelRegistry.get("mock") is not None


class TestGetWalletAddress:

    def test_known_wallet(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS):
            addr = x402_mod.get_wallet_address("buyer")
            assert addr == "0xBUYER"

    def test_unknown_wallet(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS):
            addr = x402_mod.get_wallet_address("unknown")
            assert addr is None


class TestX402Pay:

    def test_unknown_from_returns_error(self):
        with patch.object(x402_mod, "load_wallets", return_value={}):
            success, tx, info = x402_mod.x402_pay("unknown", "seller", 0.01, "o1", channel_id="mock")
            assert success is False

    def test_unknown_to_returns_error(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS):
            success, tx, info = x402_mod.x402_pay("buyer", "unknown", 0.01, "o1", channel_id="mock")
            assert success is False

    def test_mock_channel_payment(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", channel_id="mock")
            assert success is True

    def test_unknown_channel_returns_error(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", channel_id="nonexistent")
            assert success is False

    def test_no_private_key_returns_error(self):
        wallets_no_key = {"buyer": {"address": "0xB"}, "seller": {"address": "0xS"}}
        with patch.object(x402_mod, "load_wallets", return_value=wallets_no_key), \
             patch.object(x402_mod, "get_wallet_key", return_value=""):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", channel_id="mock")
            assert success is False


class TestVerifyX402Payment:

    def test_verify_with_mock_channel_after_payment(self):
        """Verify requires a prior payment on the same mock channel instance."""
        mock_ch = ChannelRegistry.get("mock")
        mock_ch.set_balance("0xBUYER", Decimal("1.0"))
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"):
            # First make a payment
            success, tx_hash, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", channel_id="mock")
            assert success is True
            # Now verify it
            valid, msg = x402_mod.verify_x402_payment(info)
            assert valid is True

    def test_verify_unknown_channel(self):
        info = {"channel_id": "nonexistent"}
        valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False


class TestGetBnbBalance:

    def test_returns_balance_from_channel(self):
        bal = x402_mod.get_bnb_balance("0xB")
        assert isinstance(bal, float)


class TestEscrowLock:

    def test_escrow_lock_with_mock(self):
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS):
            success, escrow_id, info = x402_mod.escrow_lock("buyer", "seller", 0.01, "o1", channel_id="mock")
            assert success is True

    def test_escrow_lock_unknown_wallet(self):
        with patch.object(x402_mod, "load_wallets", return_value={}):
            success, escrow_id, info = x402_mod.escrow_lock("unknown", "seller", 0.01, "o1")
            assert success is False


class TestEscrowRelease:

    def test_escrow_release_after_lock(self):
        """Release requires a prior escrow lock on the same instance."""
        mock_ch = ChannelRegistry.get("mock")
        mock_ch.set_balance("0xBUYER", Decimal("1.0"))
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xSKEY"):
            # First lock escrow
            lock_ok, escrow_id, lock_info = x402_mod.escrow_lock("buyer", "seller", 0.01, "o1", channel_id="mock")
            assert lock_ok is True
            # Now release it
            success, tx, info = x402_mod.escrow_release(escrow_id, "seller", channel_id="mock")
            assert success is True


class TestEscrowRefund:

    def test_escrow_refund_after_lock(self):
        """Refund requires a prior escrow lock on the same instance."""
        mock_ch = ChannelRegistry.get("mock")
        mock_ch.set_balance("0xBUYER", Decimal("1.0"))
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"):
            # First lock escrow
            lock_ok, escrow_id, lock_info = x402_mod.escrow_lock("buyer", "seller", 0.01, "o2", channel_id="mock")
            assert lock_ok is True
            # Now refund it
            success, tx, info = x402_mod.escrow_refund(escrow_id, "buyer", channel_id="mock")
            assert success is True