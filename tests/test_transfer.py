"""Tests for transfer — get_balance, transfer, _notify_dashboard (mocked Web3)."""
import sys
from unittest.mock import patch, MagicMock
import pytest


def _make_mock_web3():
    mock_w3 = MagicMock()
    mock_w3.to_checksum_address = lambda x: x
    mock_w3.to_wei = lambda v, u: int(float(v) * 1e18)
    mock_w3.from_wei = lambda v, u: float(v) / 1e18
    mock_w3.is_connected.return_value = True
    mock_w3.eth.get_balance.return_value = 10**18
    mock_w3.eth.get_transaction_count.return_value = 1
    mock_w3.eth.gas_price = 5 * 10**9
    mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"\x00")
    mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xtx1")
    mock_w3.eth.wait_for_transaction_receipt.return_value = MagicMock(status=1)
    return mock_w3


MOCK_WALLETS = {
    "gangdan": {"address": "0xGANGDAN"},
    "choudan": {"address": "0xCHOUDAN"},
}


@pytest.fixture(autouse=True)
def _mock_web3_module():
    """Pre-import mock for Web3, eth_account, and config to prevent real chain calls."""
    mock_w3_instance = _make_mock_web3()
    mock_w3_mod = MagicMock()
    mock_w3_mod.Web3.return_value = mock_w3_instance
    mock_w3_mod.middleware = MagicMock()

    mock_account_mod = MagicMock()

    with patch.dict(sys.modules, {
        "web3": mock_w3_mod,
        "web3.middleware": MagicMock(),
        "eth_account": mock_account_mod,
    }):
        yield


class TestGetBalance:

    def test_known_agent_returns_balance(self):
        mock_w3 = _make_mock_web3()
        mock_w3.eth.get_balance.return_value = 2 * 10**18

        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", mock_w3):
            from transfer import get_balance
            result = get_balance("gangdan")
            assert result == 2.0

    def test_unknown_agent_returns_none(self):
        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", _make_mock_web3()):
            from transfer import get_balance
            result = get_balance("nonexistent")
            assert result is None


class TestGetAllBalances:

    def test_lists_all_wallets(self):
        mock_w3 = _make_mock_web3()
        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", mock_w3):
            from transfer import get_all_balances
            get_all_balances()  # just verify no crash


class TestTransfer:

    def test_unknown_sender_returns_none(self):
        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", _make_mock_web3()):
            from transfer import transfer
            result = transfer("nonexistent", "choudan", 0.01)
            assert result is None

    def test_unknown_receiver_returns_none(self):
        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", _make_mock_web3()):
            from transfer import transfer
            result = transfer("gangdan", "nonexistent", 0.01)
            assert result is None

    def test_insufficient_balance_returns_none(self):
        mock_w3 = _make_mock_web3()
        mock_w3.eth.get_balance.return_value = 100  # very low balance

        with patch("transfer.load_wallets", return_value=MOCK_WALLETS), \
             patch("transfer.w3", mock_w3), \
             patch("transfer.get_wallet_key", return_value="0xKEY"):
            from transfer import transfer
            result = transfer("gangdan", "choudan", 100)
            assert result is None


class TestNotifyDashboard:

    def test_notify_success(self):
        mock_resp = MagicMock()
        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("transfer.load_wallets", return_value=MOCK_WALLETS):
            from transfer import _notify_dashboard
            _notify_dashboard("gangdan", "choudan", 0.01, "test", "0xTX")

    def test_notify_failure_does_not_raise(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")), \
             patch("transfer.load_wallets", return_value=MOCK_WALLETS):
            from transfer import _notify_dashboard
            # Should not raise even if the HTTP call fails
            _notify_dashboard("gangdan", "choudan", 0.01, "test", "0xTX")