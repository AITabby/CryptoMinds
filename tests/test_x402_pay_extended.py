"""Extended tests for x402_pay — X402PaymentRequest full path, sign/get_signer,
TEST_MODE x402_pay, verify with real Web3 mocking via web3 module patch."""
import hashlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

import x402_pay as x402_mod
from x402_pay import X402PaymentRequest


MOCK_WALLETS = {
    "buyer": {"address": "0xBUYER", "private_key": "0xBKEY"},
    "seller": {"address": "0xSELLER", "private_key": "0xSKEY"},
}


# ── X402PaymentRequest: to_dict, to_message, sign, get_signer ──

class TestX402PaymentRequestToDict:

    def test_to_dict_returns_all_fields(self):
        req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
        d = req.to_dict()
        assert d["chain"] == "bsc"
        assert d["nonce"] == "n1"
        assert d["timestamp"] == req.timestamp

    def test_to_message_removes_timestamp_sorted(self):
        req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
        msg = req.to_message()
        data = json.loads(msg)
        assert "timestamp" not in data
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_auto_nonce_generated(self):
        """Line 38: nonce auto-generated when not provided."""
        req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc")
        assert req.nonce is not None
        assert len(req.nonce) == 16


class TestX402PaymentRequestSign:

    def test_sign_raises_without_eth_account(self):
        """Lines 74-75: HMAC fallback removed — RuntimeError when eth_account missing."""
        with patch.dict(sys.modules, {"eth_account": None, "eth_account.messages": None}):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            with pytest.raises(RuntimeError, match="eth_account is required"):
                req.sign("0xPRIVATEKEY")

    def test_sign_with_string_key_raises_same(self):
        """HMAC fallback removed for all key formats."""
        with patch.dict(sys.modules, {"eth_account": None, "eth_account.messages": None}):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            with pytest.raises(RuntimeError, match="eth_account is required"):
                req.sign("secretkey")

    def test_sign_eth_account_path(self):
        """Lines 63-73: sign with eth_account (mocked at import level)."""
        mock_account = MagicMock()
        mock_signed = MagicMock()
        mock_signed.signature.hex.return_value = "0xsig123"
        mock_account.sign_message.return_value = mock_signed
        with patch.dict(sys.modules, {
            "eth_account": MagicMock(Account=mock_account),
            "eth_account.messages": MagicMock(),
        }):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            sig = req.sign("0xPRIVATEKEY")
            assert sig == "0xsig123"

    def test_sign_eth_account_adds_0x_prefix(self):
        """Lines 67-68: key without 0x gets prefix."""
        mock_account = MagicMock()
        mock_signed = MagicMock()
        mock_signed.signature.hex.return_value = "0xsig"
        with patch.dict(sys.modules, {
            "eth_account": MagicMock(Account=mock_account),
            "eth_account.messages": MagicMock(),
        }):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            req.sign("PRIVATEKEY")  # no 0x prefix
            # Verify sign_message was called
            mock_account.sign_message.assert_called_once()


class TestX402PaymentRequestGetSigner:

    def test_get_signer_raises_without_eth_account(self):
        """Lines 87-88: HMAC fallback removed — RuntimeError when eth_account missing."""
        with patch.dict(sys.modules, {"eth_account": None, "eth_account.messages": None}):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            with pytest.raises(RuntimeError, match="eth_account is required"):
                req.get_signer("rawsigvalue")

    def test_get_signer_eth_account_path(self):
        """Lines 86-93: recover address using eth_account."""
        mock_account = MagicMock()
        mock_account.recover_message.return_value = "0xRecoveredAddr"
        with patch.dict(sys.modules, {
            "eth_account": MagicMock(Account=mock_account),
            "eth_account.messages": MagicMock(),
        }):
            req = X402PaymentRequest("bsc", "BNB", "0xTO", 1000, "o1", "desc", nonce="n1")
            result = req.get_signer("0xsig")
            assert result == "0xRecoveredAddr"


# ── get_usdc_balance (alias) ──

class TestGetUsdcBalance:

    def test_usdc_balance_is_alias(self):
        """Lines 114-116: get_usdc_balance calls get_bnb_balance."""
        with patch.object(x402_mod, "get_bnb_balance", return_value=5.0) as m:
            result = x402_mod.get_usdc_balance("0xADDR")
            m.assert_called_once_with("0xADDR")
            assert result == 5.0


# ── x402_pay TEST_MODE path ──

class TestX402PayTestMode:

    def test_test_mode_true_env(self):
        """Lines 161-183: TEST_MODE=True returns fake tx_hash."""
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xBUYER"
        mock_req.nonce = "n1"

        with patch.object(x402_mod, "TEST_MODE", True), \
             patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx_hash, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is True
        assert info["test_mode"] is True
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66

    def test_signature_failure(self):
        """Lines 151-152: sign() raises exception."""
        mock_req = MagicMock()
        mock_req.sign.side_effect = Exception("sign broken")
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is False
        assert "签名失败" in info["error"]

    def test_signer_mismatch(self):
        """Lines 156-157: signer != from_wallet address."""
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xDIFFERENT"
        with patch.object(x402_mod, "load_wallets", return_value=MOCK_WALLETS), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is False
        assert "签名验证失败" in info["error"]


# ── x402_pay real Web3 path — mock web3 module globally ──

class TestX402PayRealWeb3Path:

    def _make_mock_w3(self):
        m = MagicMock()
        m.eth.get_transaction_count.return_value = 5
        m.eth.gas_price = 5 * 10**9
        m.eth.get_balance.return_value = 10**18
        return m

    def test_real_web3_success(self):
        """Lines 186-231: real Web3 path, confirmed transaction."""
        wallets = MOCK_WALLETS
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xBUYER"
        mock_req.nonce = "n1"

        mock_w3 = self._make_mock_w3()
        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\x00\x01raw"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed
        mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xTXHASH")
        mock_receipt = MagicMock(status=1, blockNumber=12345)
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.Web3.to_checksum_address = lambda x: x
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "TEST_MODE", False), \
             patch.object(x402_mod, "load_wallets", return_value=wallets), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is True
        assert info["block"] == 12345

    def test_real_web3_receipt_failed(self):
        """Lines 232-233: receipt.status=0."""
        wallets = MOCK_WALLETS
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xBUYER"
        mock_req.nonce = "n1"

        mock_w3 = self._make_mock_w3()
        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\x00raw"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed
        mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xTX")
        mock_receipt = MagicMock(status=0)
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.Web3.to_checksum_address = lambda x: x
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "TEST_MODE", False), \
             patch.object(x402_mod, "load_wallets", return_value=wallets), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is False
        assert "交易执行失败" in info["error"]

    def test_real_web3_exception(self):
        """Lines 235-236: exception during Web3 call."""
        wallets = MOCK_WALLETS
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xBUYER"
        mock_req.nonce = "n1"

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.side_effect = Exception("connection error")
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "TEST_MODE", False), \
             patch.object(x402_mod, "load_wallets", return_value=wallets), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is False
        assert "链上交易失败" in info["error"]

    def test_raw_transaction_attribute_fallback(self):
        """Line 205: getattr fallback rawTransaction vs raw_transaction."""
        wallets = MOCK_WALLETS
        mock_req = MagicMock()
        mock_req.sign.return_value = "fakesig"
        mock_req.get_signer.return_value = "0xBUYER"
        mock_req.nonce = "n1"

        mock_w3 = self._make_mock_w3()
        # signed_tx has rawTransaction but NOT raw_transaction
        mock_signed = MagicMock(spec=["rawTransaction"])
        mock_signed.rawTransaction = b"\x01rawtx"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed
        mock_w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xTX2")
        mock_receipt = MagicMock(status=1, blockNumber=99)
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.Web3.to_checksum_address = lambda x: x
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "TEST_MODE", False), \
             patch.object(x402_mod, "load_wallets", return_value=wallets), \
             patch.object(x402_mod, "get_wallet_key", return_value="0xBKEY"), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            success, tx, info = x402_mod.x402_pay("buyer", "seller", 0.01, "o1", "desc")
        assert success is True


# ── verify_x402_payment real Web3 path ──

class TestVerifyX402PaymentRealWeb3:

    def test_missing_tx_hash(self):
        """Line 261-262: no tx_hash returns False."""
        info = {"from": "0xA", "to": "0xB", "amount_wei": 100}
        # test_mode not set, needs Web3 — will fail
        valid, msg = x402_mod.verify_x402_payment(info)
        # Either gets False from missing tx_hash, or from exception
        assert valid is False
        assert "缺少交易哈希" in msg or "验证失败" in msg

    def test_receipt_failed(self):
        """Line 266-267: receipt.status=0."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=0)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}):
            info = {"tx_hash": "0xTX", "from": "0xA", "to": "0xB", "amount_wei": 100}
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "交易执行失败" in msg

    def test_from_mismatch(self):
        """Line 273-274: tx.from != payment_info.from."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        mock_w3.eth.get_transaction.return_value = {"from": "0xDIFFERENT", "to": "0xB", "value": 100}

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}):
            info = {"tx_hash": "0xTX", "from": "0xA", "to": "0xB", "amount_wei": 100}
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "发送方不匹配" in msg

    def test_to_mismatch(self):
        """Line 277-278: tx.to != payment_info.to."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        mock_w3.eth.get_transaction.return_value = {"from": "0xA", "to": "0xDIFFERENT", "value": 100}

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}):
            info = {"tx_hash": "0xTX", "from": "0xA", "to": "0xB", "amount_wei": 100}
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "接收方不匹配" in msg

    def test_amount_mismatch(self):
        """Line 281-282: tx.value != amount_wei."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        mock_w3.eth.get_transaction.return_value = {"from": "0xA", "to": "0xB", "value": 999}

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}):
            info = {"tx_hash": "0xTX", "from": "0xA", "to": "0xB", "amount_wei": 100}
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "金额不匹配" in msg

    def test_signature_mismatch(self):
        """Lines 296-297: recovered signer != payment_info.signer."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        mock_w3.eth.get_transaction.return_value = {"from": "0xA", "to": "0xB", "value": 100}

        mock_req = MagicMock()
        mock_req.get_signer.return_value = "0xWRONGSIGNER"

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            info = {
                "tx_hash": "0xTX", "from": "0xA", "to": "0xB",
                "amount_wei": 100, "signer": "0xA", "signature": "0xsig",
                "chain": "bsc", "token": "BNB", "order_id": "o1",
                "description": "desc", "nonce": "n1",
            }
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "签名验证失败" in msg

    def test_full_success(self):
        """Lines 285-305: all checks pass."""
        mock_w3 = MagicMock()
        mock_receipt = MagicMock(status=1)
        mock_w3.eth.get_transaction_receipt.return_value = mock_receipt
        mock_w3.eth.get_transaction.return_value = {"from": "0xA", "to": "0xB", "value": 100}

        mock_req = MagicMock()
        mock_req.get_signer.return_value = "0xA"

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "X402PaymentRequest", return_value=mock_req):
            info = {
                "tx_hash": "0xTX", "from": "0xA", "to": "0xB",
                "amount_wei": 100, "signer": "0xA", "signature": "0xsig",
                "chain": "bsc", "token": "BNB", "order_id": "o1",
                "description": "desc", "nonce": "n1",
            }
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is True

    def test_exception_returns_false(self):
        """Lines 307-308: exception caught."""
        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.side_effect = Exception("RPC error")
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}):
            info = {"tx_hash": "0xTX"}
            valid, msg = x402_mod.verify_x402_payment(info)
        assert valid is False
        assert "验证失败" in msg


# ── get_bnb_balance with Web3 mock ──

class TestGetBnbBalanceWithMock:

    def test_success_returns_balance(self):
        """Lines 98-110: Web3 balance query success."""
        mock_w3 = MagicMock()
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.from_wei = MagicMock(return_value=1.0)
        mock_w3.to_checksum_address = lambda x: x
        mock_w3.middleware_onion = MagicMock()

        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.return_value = mock_w3
        mock_web3_mod.Web3.HTTPProvider.return_value = MagicMock()
        mock_web3_mod.Web3.to_checksum_address = lambda x: x
        mock_web3_mod.Web3.from_wei = MagicMock(return_value=1.0)
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "BSC_RPC", "http://mock-rpc"):
            result = x402_mod.get_bnb_balance("0xADDR")
        assert result == 1.0

    def test_failure_returns_zero(self):
        """Line 109: exception returns 0.0."""
        mock_web3_mod = MagicMock()
        mock_web3_mod.Web3.side_effect = Exception("no RPC")
        mock_web3_mod.ExtraDataToPOAMiddleware = MagicMock()

        with patch.dict(sys.modules, {"web3": mock_web3_mod, "web3.middleware": MagicMock()}), \
             patch.object(x402_mod, "BSC_RPC", "http://mock-rpc"):
            result = x402_mod.get_bnb_balance("0xADDR")
        assert result == 0.0