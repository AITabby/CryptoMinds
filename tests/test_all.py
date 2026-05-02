"""Smoke tests for core CryptoMinds imports and runtime wiring."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_config_imports():
    from config import BSC_RPC, BSC_USDC

    assert BSC_RPC
    assert BSC_USDC


def test_orchestrator_sdk_imports():
    from orchestrator import discover_skills, get_installed_skills, purchase_skill, run_skill

    assert callable(discover_skills)
    assert callable(get_installed_skills)
    assert callable(purchase_skill)
    assert callable(run_skill)


def test_agent_runtimes_registered():
    from agent_runtimes import RUNTIMES

    assert "tiedan" in RUNTIMES
    assert "choudan" in RUNTIMES
    assert "ludan" in RUNTIMES
    assert "four_meme" in RUNTIMES


def test_x402_pay_imports():
    from x402_pay import get_usdc_balance, verify_x402_payment, x402_pay

    assert callable(x402_pay)
    assert callable(verify_x402_payment)
    assert callable(get_usdc_balance)


def test_wallets_fixture_when_present():
    wallets_path = ROOT / "wallets.json"
    if not wallets_path.exists():
        pytest.skip("wallets.json is a local secret fixture and is not required in CI")

    wallets = json.loads(wallets_path.read_text())
    assert "gangdan" in wallets
    assert "tiedan" in wallets
    assert "choudan" in wallets


def test_agent_server_imports():
    from agents.agent_server import AGENT_PORTS, AgentHandler

    assert AgentHandler is not None
    assert "tiedan" in AGENT_PORTS


def test_reputation_system_imports():
    from agents.agent_reputation import get_reputation_system

    assert get_reputation_system() is not None


def test_smart_router_imports():
    from agentpay_sdk.smart_router import SmartRouter

    assert SmartRouter() is not None


def test_multi_chain_wallet_imports():
    from agentpay_sdk.multi_chain_wallet import MultiChainWallet

    assert MultiChainWallet() is not None
