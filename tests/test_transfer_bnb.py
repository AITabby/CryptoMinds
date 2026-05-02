"""Tests for transfer_bnb — BNB transfer with mocked Web3."""
import sys
from unittest.mock import patch, MagicMock, PropertyMock
import pytest


def _make_mock_web3():
    """Create a mock Web3 module with all needed eth methods."""
    mock_w3 = MagicMock()
    mock_w3.to_checksum_address = lambda x: x
    mock_w3.to_wei = lambda v, u: int(float(v) * 1e18)
    mock_w3.from_wei = lambda v, u: float(v) / 1e18
    mock_w3.is_connected.return_value = True
    mock_w3.eth.get_transaction_count.return_value = 1
    mock_w3.eth.gas_price = 5000000000
    mock_w3.eth.account.sign_transaction.return_value = MagicMock(
        raw_transaction=b"\x00\x01"
    )
    mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xtx1")
    mock_w3.eth.wait_for_transaction_receipt.return_value = MagicMock(status=1)
    return mock_w3


MOCK_WALLETS = {
    "sender": {"address": "0xSENDER", "private_key": "0xSENDERKEY"},
    "receiver": {"address": "0xRECEIVER", "private_key": "0xRECEIVERKEY"},
}


@pytest.fixture(autouse=True)
def _mock_web3_module():
    """Pre-import mock: patch sys.modules so transfer_bnb can import."""
    mock_w3_mod = MagicMock()
    mock_w3_mod.Web3.return_value = _make_mock_web3()
    mock_w3_mod.middleware = MagicMock()
    with patch.dict(sys.modules, {
        "web3": mock_w3_mod,
        "web3.middleware": MagicMock(),
        "eth_account": MagicMock(),
    }):
        yield


class TestTransferBnb:

    def test_wallet_not_found(self):
        with patch("config.load_wallets", return_value={}):
            from transfer_bnb import transfer_bnb
            result = transfer_bnb("nonexistent", "0xTO", 0.01)
            assert result["ok"] is False
            assert "不存在" in result["error"]

    def test_successful_transfer(self):
        mock_w3 = _make_mock_web3()
        receipt = MagicMock(status=1)
        mock_w3.eth.wait_for_transaction_receipt.return_value = receipt

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("transfer_bnb.w3", mock_w3):
            from transfer_bnb import transfer_bnb
            result = transfer_bnb("sender", "0xRECEIVER", 0.01)
            assert result["ok"] is True
            assert "txHash" in result

    def test_failed_receipt(self):
        mock_w3 = _make_mock_web3()
        receipt = MagicMock(status=0)
        mock_w3.eth.wait_for_transaction_receipt.return_value = receipt

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("transfer_bnb.w3", mock_w3):
            from transfer_bnb import transfer_bnb
            result = transfer_bnb("sender", "0xRECEIVER", 0.01)
            assert result["ok"] is False
            assert "交易失败" in result["error"]