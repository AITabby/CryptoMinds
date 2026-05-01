"""Tests for AgentRegistry — register, search, stats, sqlite bridge."""
from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from agent.registry import AgentRegistry
from agent.capability import AgentCapability, CapabilitySpec, ReputationInfo


@pytest.fixture(autouse=True)
def _clear_registry():
    AgentRegistry.clear()
    AgentRegistry._sqlite_bridge = None
    AgentRegistry._persistence_path = None
    yield
    AgentRegistry.clear()
    AgentRegistry._sqlite_bridge = None
    AgentRegistry._persistence_path = None


def _make_agent(agent_id="test-1", name="TestAgent", wallet="0xABC",
                score=4.5, tasks=10, online=True, task_type="token_delivery",
                chains=["mock"], channels=["mock"], staked=Decimal("1.0")):
    return AgentCapability(
        agent_id=agent_id,
        name=name,
        wallet=wallet,
        capabilities=[
            CapabilitySpec(
                task_type=task_type,
                verification_gate=task_type,
                supported_chains=chains,
                supported_channels=channels,
                pricing_model="fixed",
                base_price=Decimal("0.001"),
            )
        ],
        reputation=ReputationInfo(score=score, tasks_completed=tasks),
        staked=staked,
        online=online,
    )


class TestRegister:

    def test_register_basic(self):
        agent = _make_agent()
        AgentRegistry.register(agent)
        assert AgentRegistry.get("test-1") is agent

    def test_empty_id_raises(self):
        agent = _make_agent(agent_id="")
        with pytest.raises(ValueError):
            AgentRegistry.register(agent)

    def test_wallet_index(self):
        agent = _make_agent(wallet="0xDEF")
        AgentRegistry.register(agent)
        assert AgentRegistry.get_by_wallet("0xdef") is agent

    def test_duplicate_overwrites(self):
        a1 = _make_agent(name="First")
        a2 = _make_agent(name="Second")
        AgentRegistry.register(a1)
        AgentRegistry.register(a2)
        assert AgentRegistry.get("test-1").name == "Second"

    def test_sqlite_bridge_called(self):
        bridge = MagicMock()
        AgentRegistry.set_sqlite_bridge(bridge)
        agent = _make_agent()
        AgentRegistry.register(agent)
        bridge.save_agent.assert_called_once_with(agent)


class TestUnregister:

    def test_unregister_existing(self):
        agent = _make_agent()
        AgentRegistry.register(agent)
        assert AgentRegistry.unregister("test-1") is True
        assert AgentRegistry.get("test-1") is None

    def test_unregister_nonexistent(self):
        assert AgentRegistry.unregister("nope") is False

    def test_wallet_index_cleared(self):
        agent = _make_agent(wallet="0xGGG")
        AgentRegistry.register(agent)
        AgentRegistry.unregister("test-1")
        assert AgentRegistry.get_by_wallet("0xggg") is None

    def test_sqlite_bridge_called_on_unregister(self):
        bridge = MagicMock()
        AgentRegistry.set_sqlite_bridge(bridge)
        agent = _make_agent(wallet="0xHHH")
        AgentRegistry.register(agent)
        AgentRegistry.unregister("test-1")
        bridge.remove_agent.assert_called_once_with("test-1", "0xHHH")


class TestSearch:

    def test_search_by_task_type(self):
        AgentRegistry.register(_make_agent(task_type="token_delivery"))
        AgentRegistry.register(_make_agent(agent_id="test-2", task_type="data_delivery"))
        results = AgentRegistry.search(task_type="token_delivery", online_only=False)
        assert len(results) == 1

    def test_search_by_chain(self):
        AgentRegistry.register(_make_agent(chains=["bsc"]))
        AgentRegistry.register(_make_agent(agent_id="test-2", chains=["eth"]))
        results = AgentRegistry.search(task_type="token_delivery", chain="bsc", online_only=False)
        assert len(results) == 1

    def test_search_min_reputation(self):
        AgentRegistry.register(_make_agent(score=5.0))
        AgentRegistry.register(_make_agent(agent_id="test-2", score=1.0))
        results = AgentRegistry.search(min_reputation=3.0, online_only=False)
        assert len(results) == 1

    def test_search_online_only(self):
        AgentRegistry.register(_make_agent(online=True))
        AgentRegistry.register(_make_agent(agent_id="test-2", online=False))
        results = AgentRegistry.search(online_only=True)
        assert len(results) == 1

    def test_search_limit(self):
        for i in range(5):
            AgentRegistry.register(_make_agent(agent_id=f"test-{i}", online=True))
        results = AgentRegistry.search(limit=3, online_only=True)
        assert len(results) == 3

    def test_sort_by_reputation(self):
        AgentRegistry.register(_make_agent(score=3.0))
        AgentRegistry.register(_make_agent(agent_id="test-2", score=5.0))
        results = AgentRegistry.search(sort_by="reputation", online_only=True)
        assert results[0].reputation.score >= results[1].reputation.score


class TestFindBestMatch:

    def test_reputation_strategy(self):
        AgentRegistry.register(_make_agent(score=3.0))
        AgentRegistry.register(_make_agent(agent_id="test-2", score=5.0))
        best = AgentRegistry.find_best_match("token_delivery", "mock", Decimal("0.01"), strategy="reputation")
        assert best.reputation.score == 5.0

    def test_no_match_returns_none(self):
        assert AgentRegistry.find_best_match("unknown_type", "mock", Decimal("0.01")) is None


class TestStats:

    def test_empty_stats(self):
        stats = AgentRegistry.get_stats()
        assert stats["total"] == 0

    def test_count_online(self):
        AgentRegistry.register(_make_agent(online=True))
        AgentRegistry.register(_make_agent(agent_id="test-2", online=False))
        assert AgentRegistry.count() == 2
        assert AgentRegistry.count_online() == 1