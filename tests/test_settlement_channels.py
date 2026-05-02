"""Tests for settlement channels — BSC, ETH, SOL in test mode."""
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from settlement.base import PaymentRequest, PaymentResult
from settlement.channels.bsc_native import BSCNativeChannel
from settlement.channels.eth_native import ETHNativeChannel
from settlement.channels.sol_native import SOLNativeChannel


# ── BSC Native Channel ──

class TestBSCNativeChannelCreatePayment:

    def test_create_payment_returns_request(self):
        ch = BSCNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        assert req.from_address == "0xFROM"
        assert req.to_address == "0xTO"
        assert req.amount == Decimal("0.01")


class TestBSCNativeChannelSignPayment:

    def test_sign_payment_raises_without_eth_account(self):
        ch = BSCNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        with patch.dict("sys.modules", {"eth_account": None, "eth_account.messages": None}):
            with pytest.raises(RuntimeError, match="eth_account is required"):
                ch.sign_payment(req, "0xKEY")


class TestBSCNativeChannelExecutePayment:

    def test_execute_mock_payment(self):
        ch = BSCNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        result = ch.execute_payment(req, "fakesig", "0xKEY")
        assert result.success is True
        assert result.proof.get("test_mode") is True

    def test_execute_mock_directly(self):
        ch = BSCNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        result = ch._execute_mock(req, "fakesig")
        assert result.success is True


class TestBSCNativeChannelVerifyPayment:

    def test_verify_test_mode_passes(self):
        ch = BSCNativeChannel(test_mode=True)
        result = PaymentResult(
            success=True, channel_id="bsc-native", chain="bsc",
            from_address="0xFROM", to_address="0xTO",
            amount=Decimal("0.01"), tx_hash="0x1",
            block_number=0, proof={"test_mode": True},
        )
        valid, msg = ch.verify_payment(result)
        assert valid is True


class TestBSCNativeChannelEscrowPrepare:

    def test_prepare_create_order(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("createOrder",
            buyer="0xBUY", seller="0xSELL", amount=0.01, orderId="o1")
        assert result["method"] == "createOrder"
        assert "contract_address" in result

    def test_prepare_deliver(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("deliver",
            orderId="o1", resultData="data")
        assert result["method"] == "deliver"

    def test_prepare_confirm(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("confirm", orderId="o1")
        assert result["method"] == "confirm"

    def test_prepare_dispute(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("dispute", orderId="o1")
        assert result["method"] == "dispute"

    def test_prepare_claim_buyer_timeout(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("claimBuyerTimeout", orderId="o1")
        assert result["method"] == "claimBuyerTimeout"

    def test_prepare_claim_seller_timeout(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_prepare_contract_call("claimSellerTimeout", orderId="o1")
        assert result["method"] == "claimSellerTimeout"


class TestBSCNativeChannelEscrowLock:

    def test_escrow_lock_returns_error(self):
        ch = BSCNativeChannel(test_mode=True)
        result = ch.escrow_lock("0xBUY", "0xSELL", Decimal("0.01"), "o1")
        assert result.success is False


# ── ETH Native Channel ──

class TestETHNativeChannelCreatePayment:

    def test_create_payment_returns_request(self):
        ch = ETHNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        assert req.from_address == "0xFROM"
        assert req.chain == "eth"


class TestETHNativeChannelSignPayment:

    def test_sign_payment_raises_without_eth_account(self):
        ch = ETHNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        with patch.dict("sys.modules", {"eth_account": None, "eth_account.messages": None}):
            with pytest.raises(RuntimeError, match="eth_account is required"):
                ch.sign_payment(req, "0xKEY")


class TestETHNativeChannelExecutePayment:

    def test_execute_mock_payment(self):
        ch = ETHNativeChannel(test_mode=True)
        req = ch.create_payment("0xFROM", "0xTO", Decimal("0.01"), "o1", "test")
        result = ch.execute_payment(req, "fakesig", "0xKEY")
        assert result.success is True
        assert result.proof.get("test_mode") is True


class TestETHNativeChannelVerifyPayment:

    def test_verify_test_mode_passes(self):
        ch = ETHNativeChannel(test_mode=True)
        result = PaymentResult(
            success=True, channel_id="eth-native", chain="eth",
            from_address="0xFROM", to_address="0xTO",
            amount=Decimal("0.01"), tx_hash="0x1",
            block_number=0, proof={"test_mode": True},
        )
        valid, msg = ch.verify_payment(result)
        assert valid is True


# ── SOL Native Channel ──

class TestSOLNativeChannelCreatePayment:

    def test_create_payment_returns_request(self):
        ch = SOLNativeChannel(test_mode=True)
        req = ch.create_payment("FROM", "TO", Decimal("0.01"), "o1", "test")
        assert req.from_address == "FROM"
        assert req.chain == "sol"


class TestSOLNativeChannelSignPayment:

    def test_sign_payment_uses_hash(self):
        ch = SOLNativeChannel(test_mode=True)
        req = ch.create_payment("FROM", "TO", Decimal("0.01"), "o1", "test")
        sig = ch.sign_payment(req, "privatekey")
        assert len(sig) > 0


class TestSOLNativeChannelExecutePayment:

    def test_execute_mock_payment(self):
        ch = SOLNativeChannel(test_mode=True)
        req = ch.create_payment("FROM", "TO", Decimal("0.01"), "o1", "test")
        result = ch.execute_payment(req, "fakesig", "privatekey")
        assert result.success is True
        assert result.proof.get("test_mode") is True


class TestSOLNativeChannelVerifyPayment:

    def test_verify_test_mode_passes(self):
        ch = SOLNativeChannel(test_mode=True)
        result = PaymentResult(
            success=True, channel_id="sol-native", chain="sol",
            from_address="FROM", to_address="TO",
            amount=Decimal("0.01"), tx_hash="0x1",
            block_number=0, proof={"test_mode": True},
        )
        valid, msg = ch.verify_payment(result)
        assert valid is True


class TestSOLNativeChannelAddressValidation:

    def test_valid_sol_address_length(self):
        ch = SOLNativeChannel(test_mode=True)
        result = ch.is_address_valid("12345678901234567890123456789012345678901234")
        assert result is True

    def test_invalid_sol_address_too_short(self):
        ch = SOLNativeChannel(test_mode=True)
        result = ch.is_address_valid("short")
        assert result is False


class TestSOLNativeChannelGetBalance:

    def test_get_balance_returns_zero_in_test_mode(self):
        ch = SOLNativeChannel(test_mode=True)
        bal = ch.get_balance("anyaddress")
        assert bal == Decimal("0")