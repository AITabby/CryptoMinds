"""Tests for protocol — create_task, verify, settle, credit functions."""
from decimal import Decimal
import pytest

from verification.base import TaskInput, TaskOutput
import protocol as proto


class TestGetProtocolInfo:

    def test_returns_info_dict(self):
        info = proto.get_protocol_info()
        assert isinstance(info, dict)


class TestCreateTask:

    def test_create_task(self):
        result = proto.create_task(
            task_type="token_delivery",
            buyer_wallet="0xB",
            seller_wallet="0xS",
            amount=Decimal("0.01"),
            chain="mock",
            channel_id="mock",
        )
        assert isinstance(result, dict)


class TestVerifyTask:

    def test_verify_task(self):
        inp = TaskInput(
            task_type="token_delivery", buyer_wallet="0xB",
            chain="mock", amount=Decimal("0.01"),
        )
        out = TaskOutput(
            task_type="token_delivery", tx_hash="0x1",
            token_address="0xTKN", token_amount="100",
        )
        result = proto.verify_task("token_delivery", inp, out)
        assert result is not None


class TestSettlePayment:

    def test_settle_with_mock_channel(self):
        result = proto.settle_payment(
            channel_id="mock",
            from_address="0xB",
            to_address="0xS",
            amount=Decimal("0.01"),
            order_id="o1",
            private_key="0xKEY",
        )
        assert result is not None


class TestRecordTaskCompletion:

    def test_record_completion(self):
        result = proto.record_task_completion(
            task_id="t1",
            task_type="token_delivery",
            buyer_wallet="0xB",
            seller_wallet="0xS",
            seller_agent_id="agent1",
            chain="mock",
            amount=Decimal("0.01"),
            status=proto.TaskStatus.VERIFIED,
            score=0.8,
        )
        assert result is not None


class TestGetAgentReputation:

    def test_get_reputation(self):
        result = proto.get_agent_reputation("agent1", "0xW")
        assert isinstance(result, dict)


class TestIssueCreditCurrency:

    def test_issue_credit(self):
        result = proto.issue_credit_currency(
            issuer_agent_id="agent1",
            issuer_wallet="0xW1",
            name="Test",
            symbol="TC",
            max_supply=Decimal("1000"),
        )
        assert isinstance(result, dict)


class TestListCreditCurrencies:

    def test_list_credit(self):
        result = proto.list_credit_currencies()
        assert isinstance(result, list)


class TestSearchAgents:

    def test_search_agents(self):
        result = proto.search_agents(task_type="token_delivery", chain="mock")
        assert isinstance(result, list)