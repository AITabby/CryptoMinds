"""Tests for token_buyer — apply_slippage, buy paths (mocked Web3)."""
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
    # contract mock chain
    mock_contract = MagicMock()
    mock_w3.eth.contract.return_value = mock_contract
    return mock_w3


MOCK_WALLETS = {
    "gangdan": {"address": "0xGANGDAN", "private_key": "0xGANGDANKEY"},
    "choudan": {"address": "0xCHOUDAN", "private_key": "0xCHOUDANKEY"},
}


@pytest.fixture(autouse=True)
def _mock_web3_module():
    """Pre-import mock for Web3 to prevent real blockchain connection."""
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


class TestApplySlippage:

    def test_zero_slippage_returns_full_amount(self):
        from token_buyer import apply_slippage
        assert apply_slippage(1000, 0) == 1000

    def test_1_percent_slippage(self):
        from token_buyer import apply_slippage
        assert apply_slippage(10000, 100) == 9900

    def test_large_slippage_clamps_to_one(self):
        from token_buyer import apply_slippage
        assert apply_slippage(100, 10000) == 1

    def test_negative_slippage_returns_more(self):
        from token_buyer import apply_slippage
        # max(0, 10000 - (-100)) = max(0, 10100) = 10100
        # 1000 * 10100 // 10000 = 1010
        assert apply_slippage(1000, -100) == 1010

    def test_zero_amount_returns_one(self):
        from token_buyer import apply_slippage
        assert apply_slippage(0, 100) == 1


class TestIsGraduated:

    def test_graduated_returns_true(self):
        mock_w3 = _make_mock_web3()
        mock_contract = mock_w3.eth.contract.return_value
        # getPair returns a non-zero address
        mock_contract.functions.getPair.return_value.call.return_value = "0x1234"

        with patch("token_buyer.w3", mock_w3):
            from token_buyer import is_graduated
            result = is_graduated("0xTOKEN")
            assert result is True

    def test_not_graduated_returns_false(self):
        mock_w3 = _make_mock_web3()
        mock_contract = mock_w3.eth.contract.return_value
        # getPair returns zero address
        mock_contract.functions.getPair.return_value.call.return_value = "0x0000000000000000000000000000000000000000"

        with patch("token_buyer.w3", mock_w3):
            from token_buyer import is_graduated
            result = is_graduated("0xTOKEN")
            assert result is False


class TestWaitReceipt:

    def test_receipt_found_immediately(self):
        mock_w3 = _make_mock_web3()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt

        with patch("token_buyer.w3", mock_w3), \
             patch("time.sleep"):
            from token_buyer import wait_receipt
            result = wait_receipt(MagicMock(hex=lambda: "0x1"))
            assert result is not None

    def test_receipt_not_found_returns_none(self):
        mock_w3 = _make_mock_web3()
        mock_w3.eth.get_transaction_receipt.return_value = None

        with patch("token_buyer.w3", mock_w3), \
             patch("time.sleep"):
            from token_buyer import wait_receipt
            result = wait_receipt(MagicMock(hex=lambda: "0x1"))
            assert result is None


class TestExecuteBuy:

    def test_execute_buy_graduated_path(self):
        mock_w3 = _make_mock_web3()
        # token contract mock for balanceOf - must return int values
        mock_token_contract = MagicMock()
        mock_token_contract.functions.balanceOf.side_effect = MagicMock(
            return_value=MagicMock(call=MagicMock(side_effect=[0, 1000, 500]))
        )
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        mock_w3.eth.contract.return_value = mock_token_contract
        mock_w3.eth.get_transaction_receipt.return_value = MagicMock(status=1, gasUsed=21000)

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("token_buyer.w3", mock_w3), \
             patch("token_buyer.is_graduated", return_value=True), \
             patch("token_buyer.buy_on_pancakeswap", return_value=("0xSWAP", MagicMock(status=1))), \
             patch("token_buyer.transfer_tokens", return_value=("0xXFER", MagicMock(status=1), 1000)), \
             patch("time.sleep"):
            from token_buyer import execute_buy
            result = execute_buy("gangdan", "0xBUYER", "0xTOKEN", 0.001)
            assert result["ok"] is True
            assert result["graduated"] is True

    def test_execute_buy_fourmeme_path(self):
        # Need to mock balanceOf calls inside execute_buy
        mock_w3 = _make_mock_web3()
        mock_token_contract = MagicMock()
        # balanceOf returns ints, called multiple times (before, after, buyer)
        mock_bal_call = MagicMock(side_effect=[0, 1000, 500])
        mock_token_contract.functions.balanceOf.return_value.call = mock_bal_call
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        mock_w3.eth.contract.return_value = mock_token_contract

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("token_buyer.w3", mock_w3), \
             patch("token_buyer.is_graduated", return_value=False), \
             patch("token_buyer.buy_on_fourmeme", return_value=("0xSWAP", MagicMock(status=1))), \
             patch("token_buyer.transfer_tokens", return_value=("0xXFER", MagicMock(status=1), 1000)), \
             patch("time.sleep"):
            from token_buyer import execute_buy
            result = execute_buy("gangdan", "0xBUYER", "0xTOKEN", 0.001)
            assert result["ok"] is True
            assert result["graduated"] is False
            assert result["path"] == "four.meme"

    def test_execute_buy_swap_failure(self):
        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value="0xKEY"), \
             patch("token_buyer.w3", _make_mock_web3()), \
             patch("token_buyer.is_graduated", return_value=True), \
             patch("token_buyer.buy_on_pancakeswap", return_value=(None, None)):
            from token_buyer import execute_buy
            result = execute_buy("gangdan", "0xBUYER", "0xTOKEN", 0.001)
            assert result["ok"] is False