"""Smoke tests for core CryptoMinds imports and runtime wiring."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_config_imports():
    from config import BSC_RPC, BSC_USDC

    assert BSC_RPC
    assert BSC_USDC


def test_protocol_imports():
    from protocol import get_protocol_info, AgentRegistry, ChannelRegistry, GateRegistry

    assert callable(get_protocol_info)
    assert AgentRegistry is not None
    assert ChannelRegistry is not None
    assert GateRegistry is not None


def test_settlement_imports():
    from settlement import ChannelRegistry, init_default_channels
    from settlement.base import PaymentResult

    assert callable(init_default_channels)


def test_escrow_imports():
    from escrow import EscrowState, EscrowOrder, ArbitrationEngine
    from settlement.escrow_state import EscrowStateMachine

    assert EscrowStateMachine is not None


def test_verification_imports():
    from verification import GateRegistry, init_default_gates
    from verification.base import VerificationResult

    assert callable(init_default_gates)


def test_agent_registry_imports():
    from agent import AgentRegistry, AgentCapability, CapabilitySpec

    assert AgentRegistry is not None


def test_reputation_imports():
    from reputation import RecordStore, ReputationCalculator, CreditRegistry
    from reputation.record import PerformanceRecord, TaskStatus

    assert ReputationCalculator is not None


def test_voucher_imports():
    from voucher import VoucherState, VoucherStateMachine, Voucher, VoucherChainVerifier, UsageRecord

    assert VoucherState is not None


def test_wallets_fixture_when_present():
    wallets_path = ROOT / "wallets.json"
    if not wallets_path.exists():
        pytest.skip("wallets.json is a local secret fixture and is not required in CI")

    wallets = json.loads(wallets_path.read_text())
    assert "gangdan" in wallets
    assert "tiedan" in wallets
    assert "choudan" in wallets


def test_credit_score_imports():
    from credit_score.calculator import SacredCalculator
    from credit_score.models import SacredScore, DimensionScore

    assert SacredCalculator is not None


def test_data_store_imports():
    from data.sqlite_store import SqliteEscrowStore, SqliteRecordStore

    assert SqliteEscrowStore is not None
    assert SqliteRecordStore is not None


def test_api_app_creation():
    from api import create_app

    app = create_app()
    assert app is not None