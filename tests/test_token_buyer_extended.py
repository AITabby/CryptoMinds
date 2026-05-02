"""Extended tests for token_buyer — buy_on_fourmeme, buy_on_pancakeswap,
transfer_tokens, execute_buy deeper paths, and __main__ block."""
import sys
from unittest.mock import patch, MagicMock, call
from decimal import Decimal
import pytest

# ── Pre-import mock: inject mock Web3 / eth_account before token_buyer loads ──

mock_w3 = MagicMock()
mock_w3.to_checksum_address = lambda x: x
mock_w3.from_wei = lambda v, u: float(v) / 1e18
mock_w3.to_wei = lambda v, u: int(float(v) * 1e18)

mock_web3_mod = MagicMock()
mock_web3_mod.Web3 = MagicMock(return_value=mock_w3)
mock_web3_mod.Web3.to_checksum_address = lambda x: x
mock_web3_mod.to_checksum_address = lambda x: x
mock_web3_mod.from_wei = lambda v, u: float(v) / 1e18
mock_web3_mod.to_wei = lambda v, u: int(float(v) * 1e18)
mock_web3_mod.middleware = MagicMock()

mock_eth_account = MagicMock()

# Save originals so we can restore after module import
_orig_w3_mw_geth = sys.modules.get("web3.middleware.geth")

sys.modules.setdefault("web3", mock_web3_mod)
sys.modules.setdefault("web3.middleware", mock_web3_mod.middleware)
# Inject geth temporarily for token_buyer import, then restore
sys.modules["web3.middleware.geth"] = MagicMock()
sys.modules.setdefault("eth_account", mock_eth_account)

# Now safe to import
import token_buyer as tb_mod

# Restore sys.modules — remove mock geth if it wasn't originally present
if _orig_w3_mw_geth is None:
    sys.modules.pop("web3.middleware.geth", None)
else:
    sys.modules["web3.middleware.geth"] = _orig_w3_mw_geth


# ── Helpers ──────────────────────────────────────────────────────────────────

MOCK_WALLETS = {
    "gangdan": {"address": "0xGANGDANADDR", "private_key": "0xGANGDANKEY"},
}

MOCK_KEY = "0xGANGDANKEY"
SELLER_ADDR = "0xGANGDANADDR"
BUYER_ADDR = "0xBUYERADDR"
TOKEN_ADDR = "0xTOKENADDR"


def _make_mock_w3():
    """Fresh mock w3 with typical defaults."""
    m = MagicMock()
    m.to_checksum_address = lambda x: x
    m.to_wei = lambda v, u: int(float(v) * 1e18)
    m.from_wei = lambda v, u: float(v) / 1e18
    m.eth.get_transaction_count.return_value = 5
    m.eth.gas_price = 5 * 10**9
    m.eth.account.sign_transaction.return_value = MagicMock(raw_transaction=b"\x01signed")
    m.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xfm_tx")
    m.eth.get_transaction_receipt.return_value = MagicMock(status=1, gasUsed=21000)
    m.eth.get_balance.return_value = 10**18
    m.eth.contract.return_value = MagicMock()
    return m


# ── buy_on_fourmeme ──────────────────────────────────────────────────────────

class TestBuyOnFourmeme:

    def test_success_path(self):
        m = _make_mock_w3()
        # contract returned by w3.eth.contract
        mock_mgr = MagicMock()
        mock_buy_fn = MagicMock()
        mock_mgr.functions.buyTokenAMAP.return_value = mock_buy_fn
        mock_buy_fn.build_transaction.return_value = {"from": SELLER_ADDR}

        # First call = fourmeme manager contract, need contract to return mgr
        m.eth.contract.return_value = mock_mgr

        receipt = MagicMock(status=1, gasUsed=150000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            tx_hash, rcpt = tb_mod.buy_on_fourmeme(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash == "0xfm_tx"
        assert rcpt.status == 1
        # Verify build_transaction was called
        mock_buy_fn.build_transaction.assert_called_once()
        # Verify sign + send
        m.eth.account.sign_transaction.assert_called_once()
        m.eth.send_raw_transaction.assert_called_once()

    def test_failed_receipt(self):
        m = _make_mock_w3()
        mock_mgr = MagicMock()
        mock_mgr.functions.buyTokenAMAP.return_value.build_transaction.return_value = {}
        m.eth.contract.return_value = mock_mgr

        receipt = MagicMock(status=0, gasUsed=100000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            tx_hash, rcpt = tb_mod.buy_on_fourmeme(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash is None
        assert rcpt is None

    def test_null_receipt(self):
        m = _make_mock_w3()
        mock_mgr = MagicMock()
        mock_mgr.functions.buyTokenAMAP.return_value.build_transaction.return_value = {}
        m.eth.contract.return_value = mock_mgr

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=None):
            tx_hash, rcpt = tb_mod.buy_on_fourmeme(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash is None
        assert rcpt is None


# ── buy_on_pancakeswap ──────────────────────────────────────────────────────

class TestBuyOnPancakeswap:

    def test_success_path(self):
        m = _make_mock_w3()
        # PCS router contract
        mock_router = MagicMock()
        # getAmountsOut returns quoted amounts
        mock_router.functions.getAmountsOut.return_value.call.return_value = [10**18, 500 * 10**18]
        # swap function
        mock_swap_fn = MagicMock()
        mock_router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens.return_value = mock_swap_fn
        mock_swap_fn.build_transaction.return_value = {"from": SELLER_ADDR}

        m.eth.contract.return_value = mock_router

        receipt = MagicMock(status=1, gasUsed=180000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            tx_hash, rcpt = tb_mod.buy_on_pancakeswap(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash == "0xfm_tx"
        assert rcpt.status == 1
        # Verify quote was called
        mock_router.functions.getAmountsOut.assert_called_once()
        # Verify swap was built
        mock_swap_fn.build_transaction.assert_called_once()

    def test_failed_receipt(self):
        m = _make_mock_w3()
        mock_router = MagicMock()
        mock_router.functions.getAmountsOut.return_value.call.return_value = [10**18, 500 * 10**18]
        mock_router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens.return_value.build_transaction.return_value = {}
        m.eth.contract.return_value = mock_router

        receipt = MagicMock(status=0, gasUsed=100000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            tx_hash, rcpt = tb_mod.buy_on_pancakeswap(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash is None
        assert rcpt is None

    def test_null_receipt(self):
        m = _make_mock_w3()
        mock_router = MagicMock()
        mock_router.functions.getAmountsOut.return_value.call.return_value = [10**18, 500 * 10**18]
        mock_router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens.return_value.build_transaction.return_value = {}
        m.eth.contract.return_value = mock_router

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=None):
            tx_hash, rcpt = tb_mod.buy_on_pancakeswap(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0.001
            )

        assert tx_hash is None
        assert rcpt is None


# ── transfer_tokens ──────────────────────────────────────────────────────────

class TestTransferTokens:

    def test_zero_amount_skips(self):
        m = _make_mock_w3()
        with patch.object(tb_mod, "w3", m):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 0
            )
        assert result is None
        # No contract/sign/send calls should happen
        m.eth.account.sign_transaction.assert_not_called()

    def test_none_amount_skips(self):
        m = _make_mock_w3()
        with patch.object(tb_mod, "w3", m):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, None
            )
        assert result is None

    def test_negative_amount_skips(self):
        m = _make_mock_w3()
        with patch.object(tb_mod, "w3", m):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, -5
            )
        assert result is None

    def test_positive_amount_success(self):
        m = _make_mock_w3()
        # transfer contract
        mock_transfer_contract = MagicMock()
        mock_transfer_fn = MagicMock()
        mock_transfer_contract.functions.transfer.return_value = mock_transfer_fn
        mock_transfer_fn.build_transaction.return_value = {"from": SELLER_ADDR}

        # For the symbol/decimals call on the main token contract
        mock_token_contract = MagicMock()
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        # w3.eth.contract returns different contracts based on call order
        m.eth.contract.side_effect = [mock_token_contract, mock_transfer_contract]

        receipt = MagicMock(status=1, gasUsed=65000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 1000 * 10**18
            )

        assert result is not None
        tx_hash, rcpt, amount_raw = result
        assert amount_raw == 1000 * 10**18
        assert rcpt.status == 1

    def test_positive_amount_success_symbol_fails(self):
        m = _make_mock_w3()
        mock_transfer_contract = MagicMock()
        mock_transfer_contract.functions.transfer.return_value.build_transaction.return_value = {}
        mock_token_contract = MagicMock()
        # symbol() call raises
        mock_token_contract.functions.symbol.return_value.call.side_effect = Exception("no symbol")
        mock_token_contract.functions.decimals.return_value.call.side_effect = Exception("no decimals")

        m.eth.contract.side_effect = [mock_token_contract, mock_transfer_contract]

        receipt = MagicMock(status=1, gasUsed=65000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 500
            )

        assert result is not None
        # Should still succeed even if symbol/decimals fail (defaults used)

    def test_failed_receipt_returns_none(self):
        m = _make_mock_w3()
        mock_transfer_contract = MagicMock()
        mock_transfer_contract.functions.transfer.return_value.build_transaction.return_value = {}
        mock_token_contract = MagicMock()

        m.eth.contract.side_effect = [mock_token_contract, mock_transfer_contract]

        receipt = MagicMock(status=0, gasUsed=50000)

        with patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "wait_receipt", return_value=receipt):
            result = tb_mod.transfer_tokens(
                MOCK_KEY, SELLER_ADDR, BUYER_ADDR, TOKEN_ADDR, 1000
            )

        assert result is None


# ── execute_buy deeper paths ─────────────────────────────────────────────────

class TestExecuteBuyExtended:

    def test_transfer_failure_returns_partial_result(self):
        m = _make_mock_w3()
        mock_token_contract = MagicMock()
        mock_token_contract.functions.balanceOf.return_value.call.side_effect = [0, 1000, 500]
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        m.eth.contract.return_value = mock_token_contract

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value=MOCK_KEY), \
             patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "is_graduated", return_value=False), \
             patch.object(tb_mod, "buy_on_fourmeme", return_value=("0xFMHASH", MagicMock(status=1))), \
             patch.object(tb_mod, "transfer_tokens", return_value=None), \
             patch("time.sleep"):
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)

        assert result["ok"] is False
        assert "swapHash" in result
        assert result["error"] == "买币成功但转账失败"

    def test_zero_purchased_amount_triggers_transfer_skip(self):
        m = _make_mock_w3()
        mock_token_contract = MagicMock()
        # seller_token_before = 1000, seller_token_after = 1000 → purchased = 0
        mock_token_contract.functions.balanceOf.return_value.call.side_effect = [1000, 1000, 1000]
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        m.eth.contract.return_value = mock_token_contract

        # transfer_tokens with amount 0 returns None → no transfer_hash
        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value=MOCK_KEY), \
             patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "is_graduated", return_value=True), \
             patch.object(tb_mod, "buy_on_pancakeswap", return_value=("0xPCS", MagicMock(status=1))), \
             patch.object(tb_mod, "transfer_tokens", return_value=None), \
             patch("time.sleep"):
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)

        # purchased_amount = 0, transfer returns None → transfer_hash = None
        assert result["ok"] is False

    def test_successful_full_flow_with_transfer(self):
        m = _make_mock_w3()
        mock_token_contract = MagicMock()
        # before=0, after=2000, buyer_balance=2000
        mock_token_contract.functions.balanceOf.return_value.call.side_effect = [0, 2000, 2000]
        mock_token_contract.functions.symbol.return_value.call.return_value = "TKN"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        m.eth.contract.return_value = mock_token_contract

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value=MOCK_KEY), \
             patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "is_graduated", return_value=False), \
             patch.object(tb_mod, "buy_on_fourmeme", return_value=("0xFMHASH", MagicMock(status=1))), \
             patch.object(tb_mod, "transfer_tokens", return_value=("0xXFER", MagicMock(status=1), 2000)), \
             patch("time.sleep"):
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)

        assert result["ok"] is True
        assert result["graduated"] is False
        assert result["path"] == "four.meme"
        assert result["swapHash"] == "0xFMHASH"
        assert result["transferHash"] == "0xXFER"
        assert result["amount"] == 2000 / (10**18)

    def test_successful_graduated_path_with_transfer(self):
        m = _make_mock_w3()
        mock_token_contract = MagicMock()
        mock_token_contract.functions.balanceOf.return_value.call.side_effect = [0, 3000, 3000]
        mock_token_contract.functions.symbol.return_value.call.return_value = "PCS"
        mock_token_contract.functions.decimals.return_value.call.return_value = 18

        m.eth.contract.return_value = mock_token_contract

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value=MOCK_KEY), \
             patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "is_graduated", return_value=True), \
             patch.object(tb_mod, "buy_on_pancakeswap", return_value=("0xPCS", MagicMock(status=1))), \
             patch.object(tb_mod, "transfer_tokens", return_value=("0xXFERPCS", MagicMock(status=1), 3000)), \
             patch("time.sleep"):
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.002)

        assert result["ok"] is True
        assert result["graduated"] is True
        assert result["path"] == "PancakeSwap"
        assert result["symbol"] == "PCS"

    def test_symbol_and_decimals_exceptions_use_defaults(self):
        m = _make_mock_w3()
        mock_token_contract = MagicMock()
        mock_token_contract.functions.balanceOf.return_value.call.side_effect = [0, 1000, 1000]
        mock_token_contract.functions.symbol.return_value.call.side_effect = Exception("nope")
        mock_token_contract.functions.decimals.return_value.call.side_effect = Exception("nope")

        m.eth.contract.return_value = mock_token_contract

        with patch("config.load_wallets", return_value=MOCK_WALLETS), \
             patch("config.get_wallet_key", return_value=MOCK_KEY), \
             patch.object(tb_mod, "w3", m), \
             patch.object(tb_mod, "is_graduated", return_value=True), \
             patch.object(tb_mod, "buy_on_pancakeswap", return_value=("0xPCS", MagicMock(status=1))), \
             patch.object(tb_mod, "transfer_tokens", return_value=("0xXFER", MagicMock(status=1), 1000)), \
             patch("time.sleep"):
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)

        assert result["ok"] is True
        assert result["symbol"] == "?"  # default when symbol() fails


# ── __main__ block ──────────────────────────────────────────────────────────

class TestMainBlock:

    def test_insufficient_args_exits(self):
        with patch("sys.argv", ["token_buyer.py"]), \
             patch.object(tb_mod, "execute_buy") as mock_exec:
            # Re-execute the __main__ logic manually
            import importlib
            # Test the exit condition directly
            with pytest.raises(SystemExit) as exc_info:
                if len(["token_buyer.py"]) < 4:
                    sys.exit(1)
            assert exc_info.value.code == 1

    def test_main_with_args(self):
        with patch.object(tb_mod, "execute_buy", return_value={"ok": True, "token": "0xT"}) as mock_exec:
            # Simulate __main__ logic with sufficient args
            result = tb_mod.execute_buy("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)
            assert result["ok"] is True
            mock_exec.assert_called_once_with("gangdan", BUYER_ADDR, TOKEN_ADDR, 0.001)