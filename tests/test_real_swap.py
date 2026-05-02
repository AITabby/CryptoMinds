"""Tests for real_swap — main() branches (mocked Web3 + config)."""
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
    mock_w3.eth.wait_for_transaction_receipt.return_value = MagicMock(status=1, gasUsed=21000)
    mock_w3.eth.get_transaction_receipt.return_value = MagicMock(status=1, gasUsed=21000)
    mock_w3.eth.account.from_key.return_value = MagicMock(
        address="0xSELLER",
        sign_transaction=MagicMock(return_value=MagicMock(raw_transaction=b"\x00")),
    )
    return mock_w3


MOCK_WALLETS = {
    "gangdan": {"address": "0xGANGDAN", "private_key": "0xKEY"},
}


@pytest.fixture(autouse=True)
def _mock_web3_and_deps():
    """Pre-import mock for Web3 and eth_account."""
    mock_w3_instance = _make_mock_web3()
    mock_w3_mod = MagicMock()
    mock_w3_mod.Web3.return_value = mock_w3_instance
    mock_w3_mod.Web3.to_checksum_address = lambda x: x
    mock_w3_mod.middleware = MagicMock()

    mock_account_mod = MagicMock()

    with patch.dict(sys.modules, {
        "web3": mock_w3_mod,
        "web3.middleware": MagicMock(),
        "eth_account": mock_account_mod,
    }):
        yield


class TestRealSwapMainUnknownSeller:

    def test_unknown_seller_calls_sys_exit(self):
        """When seller not found, main() calls sys.exit(1).
        Since we mock sys.exit, the function continues — test that exit was called."""
        with patch("config.load_wallets", return_value={}), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("config.BSC_RPC", "http://mock-rpc"), \
             patch("sys.argv", ["real_swap.py", "unknown", "0xBUYER", "0.001"]), \
             patch("sys.exit", side_effect=SystemExit) as mock_exit:
            from real_swap import main
            with pytest.raises(SystemExit):
                main()
            mock_exit.assert_called_with(1)


class TestRealSwapConstants:

    def test_module_loads_with_mocked_deps(self):
        """Verify module can be imported with mocked deps."""
        import importlib
        if "real_swap" in sys.modules:
            del sys.modules["real_swap"]
        import real_swap
        assert "real_swap" in sys.modules