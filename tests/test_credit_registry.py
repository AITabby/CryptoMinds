"""Tests for CreditRegistry — issue, transfer, pay, acceptance, persistence."""
from decimal import Decimal
import pytest
import tempfile
import os

from reputation.credit import CreditRegistry, CreditCurrency, CreditBalance


class TestCreditCurrencyToDict:

    def test_to_dict_fields(self):
        c = CreditCurrency(
            currency_id="c1", issuer_agent_id="agent1", issuer_wallet="0xW",
            name="Test Credit", symbol="TC", total_supply=Decimal("1000"),
        )
        d = c.to_dict()
        assert d["currency_id"] == "c1"
        assert d["symbol"] == "TC"
        assert d["total_supply"] == "1000"


class TestCreditBalanceToDict:

    def test_to_dict_fields(self):
        b = CreditBalance(currency_id="c1", wallet="0xW", balance=Decimal("50"))
        d = b.to_dict()
        assert d["balance"] == "50"


class TestCreditRegistryIssue:

    def test_issue_success(self):
        reg = CreditRegistry()
        result = reg.issue("agent1", "0xW1", "Meme Credit", "MC", Decimal("1000"))
        assert result["ok"] is True
        assert result["currency_id"] is not None

    def test_issue_duplicate_wallet_fails(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "First", "F1", Decimal("1000"))
        result = reg.issue("agent1", "0xW1", "Second", "S1", Decimal("1000"))
        assert "error" in result

    def test_issue_initial_balance_to_issuer(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        bal = reg.get_balance(cid, "0xW1")
        assert bal == Decimal("1000")


class TestCreditRegistryTransfer:

    def test_transfer_success(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.transfer(cid, "0xW1", "0xW2", Decimal("100"))
        assert result["ok"] is True

    def test_transfer_insufficient_balance(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.transfer(cid, "0xW1", "0xW2", Decimal("5000"))
        assert "error" in result

    def test_transfer_unknown_currency(self):
        reg = CreditRegistry()
        result = reg.transfer("unknown", "0xW1", "0xW2", Decimal("100"))
        assert "error" in result


class TestCreditRegistryQueries:

    def test_get_currency(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        c = reg.get_currency(cid)
        assert c is not None
        assert c.symbol == "MC"

    def test_get_by_issuer(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        c = reg.get_by_issuer("0xW1")
        assert c is not None

    def test_list_all(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        all_c = reg.list_all()
        assert len(all_c) == 1

    def test_get_balance_zero_for_unknown(self):
        reg = CreditRegistry()
        bal = reg.get_balance("unknown", "0xW1")
        assert bal == Decimal("0")


class TestCreditRegistryAcceptReject:

    def test_accept_currency(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.accept_currency(cid, "agent2")
        assert result is True

    def test_reject_currency(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        reg.accept_currency(cid, "agent2")
        result = reg.reject_currency(cid, "agent2")
        assert result is True

    def test_list_accepted_by(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        reg.accept_currency(cid, "agent2")
        accepted = reg.list_accepted_by("agent2")
        assert len(accepted) == 1


class TestCreditRegistryPayWithCredit:

    def test_pay_success(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        reg.accept_currency(cid, "agent2")
        result = reg.pay_with_credit(cid, "0xW1", "0xW2", Decimal("100"), to_agent_id="agent2")
        assert result["ok"] is True
        assert "tx_hash" in result

    def test_pay_not_accepted(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.pay_with_credit(cid, "0xW1", "0xW2", Decimal("100"), to_agent_id="agent2")
        assert "error" in result

    def test_pay_insufficient_balance(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("100"))
        cid = list(reg._currencies.keys())[0]
        result = reg.pay_with_credit(cid, "0xW1", "0xW2", Decimal("500"))
        assert "error" in result

    def test_pay_unknown_currency(self):
        reg = CreditRegistry()
        result = reg.pay_with_credit("unknown", "0xW1", "0xW2", Decimal("100"))
        assert "error" in result


class TestCreditRegistryCheckAcceptance:

    def test_check_accepted(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        reg.accept_currency(cid, "agent2")
        result = reg.check_acceptance(cid, "agent2")
        assert result["accepted"] is True

    def test_check_not_accepted(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.check_acceptance(cid, "agent3")
        assert result["accepted"] is False


class TestCreditRegistryGetAcceptableCurrencies:

    def test_filter_by_trust_score(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        # Accept by many agents to boost trust score
        cid = list(reg._currencies.keys())[0]
        for i in range(10):
            reg.accept_currency(cid, f"agent{i}")
        result = reg.get_acceptable_currencies("agent0", min_trust_score=0.3)
        assert len(result) >= 1


class TestCreditRegistryVerifyPaymentCapability:

    def test_sufficient_balance(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        result = reg.verify_payment_capability(cid, "0xW1", Decimal("100"))
        assert result is True

    def test_insufficient_balance(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("100"))
        cid = list(reg._currencies.keys())[0]
        result = reg.verify_payment_capability(cid, "0xW1", Decimal("500"))
        assert result is False


class TestCreditRegistryTrustScore:

    def test_trust_score_with_acceptances(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        cid = list(reg._currencies.keys())[0]
        reg.accept_currency(cid, "agent2")
        score = reg.get_trust_score(cid)
        assert score > 0

    def test_trust_score_unknown_currency(self):
        reg = CreditRegistry()
        score = reg.get_trust_score("unknown")
        assert score == 0.0


class TestCreditRegistryPersistence:

    def test_persistence_roundtrip(self):
        reg = CreditRegistry()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            reg.set_persistence(path)
            reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
            cid = list(reg._currencies.keys())[0]
            reg.accept_currency(cid, "agent2")

            # Create new registry and load
            reg2 = CreditRegistry()
            reg2.set_persistence(path)
            loaded_currencies = reg2.list_all()
            assert len(loaded_currencies) == 1
        finally:
            os.unlink(path)


class TestCreditRegistryClear:

    def test_clear_empties_all(self):
        reg = CreditRegistry()
        reg.issue("agent1", "0xW1", "MC", "MC", Decimal("1000"))
        reg.clear()
        assert len(reg.list_all()) == 0