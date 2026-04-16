#!/usr/bin/env python3
"""
CryptoMinds 集成测试
验证核心模块能正常导入和运行
"""
import sys
import os
import json

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

passed = 0
failed = 0

def check(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1


print("=" * 50)
print("🧪 CryptoMinds 集成测试")
print("=" * 50)

# 1. 核心模块导入
print("\n📦 模块导入")

def test_config():
    from config import BSC_RPC, BSC_USDC
    assert BSC_RPC, "BSC_RPC 为空"
    assert BSC_USDC, "BSC_USDC 为空"

def test_orchestrator():
    from orchestrator import discover_skills, purchase_skill, run_skill, get_installed_skills
    assert callable(discover_skills)

def test_runtimes():
    from agent_runtimes import RUNTIMES
    assert "tiedan" in RUNTIMES
    assert "choudan" in RUNTIMES
    assert "ludan" in RUNTIMES
    assert "four_meme" in RUNTIMES

def test_x402_pay():
    from x402_pay import x402_pay, verify_x402_payment, get_usdc_balance
    assert callable(x402_pay)

def test_wallets():
    with open(os.path.join(DIR, "wallets.json")) as f:
        wallets = json.load(f)
    assert "gangdan" in wallets
    assert "tiedan" in wallets
    assert "choudan" in wallets

check("config", test_config)
check("orchestrator SDK", test_orchestrator)
check("agent_runtimes", test_runtimes)
check("x402_pay", test_x402_pay)
check("wallets", test_wallets)

# 2. Agent 服务导入
print("\n🤖 Agent 服务")

def test_agent_server():
    from agents.agent_server import AgentHandler, AGENT_PORTS
    assert "tiedan" in AGENT_PORTS

def test_reputation():
    from agents.agent_reputation import get_reputation_system
    rs = get_reputation_system()
    assert rs is not None

check("agent_server", test_agent_server)
check("reputation_system", test_reputation)

# 3. Smart Router
print("\n🔀 支付路由")

def test_smart_router():
    from agentpay_sdk.smart_router import SmartRouter
    router = SmartRouter()
    assert router is not None

def test_multi_chain_wallet():
    from agentpay_sdk.multi_chain_wallet import MultiChainWallet
    wallet = MultiChainWallet()
    assert wallet is not None

check("smart_router", test_smart_router)
check("multi_chain_wallet", test_multi_chain_wallet)

# 结果
print(f"\n{'=' * 50}")
print(f"结果: {passed} 通过, {failed} 失败")
if failed > 0:
    print("❌ 有测试失败！")
    sys.exit(1)
else:
    print("✅ 全部通过！")
