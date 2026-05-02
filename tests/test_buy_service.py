"""Tests for buy_service — script-level BNB transfer (pre-import mocked Web3)."""
import sys
from unittest.mock import patch, MagicMock
import pytest


def _make_mock_web3():
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.to_wei = lambda v, u: int(float(v) * 1e18)
    mock_w3.from_wei = lambda v, u: float(v) / 1e18
    mock_w3.eth.get_balance.return_value = 10**18
    mock_w3.eth.get_transaction_count.return_value = 1
    mock_w3.eth.gas_price = 5 * 10**9
    mock_w3.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"\x00")
    mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xtx1")
    mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1, "gasUsed": 21000}
    return mock_w3


MOCK_WALLETS = {
    "choudan": {"address": "0xCHOUDAN", "private_key": "0xCHOUDANKEY"},
    "gangdan": {"address": "0xGANGDAN", "private_key": "0xGANGDANKEY"},
}


@pytest.fixture(autouse=True)
def _mock_web3_and_deps():
    """Pre-import mock for Web3, config, eth_account to prevent real blockchain calls."""
    mock_w3_instance = _make_mock_web3()
    mock_w3_mod = MagicMock()
    mock_w3_mod.Web3.return_value = mock_w3_instance
    mock_w3_mod.middleware = MagicMock()

    mock_account_mod = MagicMock()

    with patch.dict(sys.modules, {
        "web3": mock_w3_mod,
        "web3.middleware": MagicMock(),
        "eth_account": mock_account_mod,
    }), \
    patch("config.BSC_RPC", "http://mock-rpc"), \
    patch("config.load_wallets", return_value=MOCK_WALLETS), \
    patch("config.get_wallet_key", return_value="0xKEY"):
        yield


class TestBuyServiceModuleImport:

    def test_module_loads_without_real_chain(self):
        """Verify that buy_service.py can be imported with mocked deps."""
        # The module runs at import time, but our mocks prevent real calls
        import importlib
        # buy_service may already be in sys.modules with a partial state,
        # force reload to ensure our mocks take effect
        if "buy_service" in sys.modules:
            del sys.modules["buy_service"]
        import buy_service
        assert "buy_service" in sys.modules

    def test_module_creates_web3_connection(self):
        """The module creates w3 at import time; verify mock was used."""
        import importlib
        if "buy_service" in sys.modules:
            del sys.modules["buy_service"]
        import buy_service
        assert buy_service.w3 is not None