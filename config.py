#!/usr/bin/env python3
"""
CryptoMinds 共享配置
所有链上 RPC、合约地址等统一在此管理，避免散落各处
"""

import json
import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WALLETS_FILE = PROJECT_ROOT / "wallets.json"

# ── BSC RPC ──────────────────────────────────────────────
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org/")

# ── PancakeSwap V2 Router ───────────────────────────────
PANCAKE_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# ── BSC USDC (替代 USDT，dataseed 查不到 USDT code) ─────
BSC_USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
BSC_USDC_DECIMALS = 18

# ── 买币保护参数 ─────────────────────────────────────────
# 默认接受 5% 滑点，生产环境可以按部署需要继续收紧
DEFAULT_SLIPPAGE_BPS = int(os.getenv("DEFAULT_SLIPPAGE_BPS", "500"))


# ── 集中式钱包加载 ──────────────────────────────────────────

@lru_cache(maxsize=1)
def load_wallets() -> dict:
    """Load and normalize wallets.json once per process."""
    if not WALLETS_FILE.exists():
        return {}
    raw = json.loads(WALLETS_FILE.read_text())
    normalized = {}
    for name, info in raw.items():
        pk = info.get("private_key") or info.get("privateKey") or info.get("key") or ""
        if pk and not pk.startswith("0x"):
            pk = "0x" + pk
        normalized[name] = {
            "address": info.get("address", ""),
            "private_key": pk,
        }
    return normalized


def get_wallet_key(name: str) -> str:
    """Get private key by wallet name. Env var overrides wallets.json."""
    env_key = os.getenv(f"WALLET_KEY_{name.upper()}")
    if env_key:
        if not env_key.startswith("0x"):
            env_key = "0x" + env_key
        return env_key
    wallets = load_wallets()
    info = wallets.get(name)
    if not info:
        return ""
    return info.get("private_key", "")


def reload_wallets():
    """Clear cache and re-read wallets from disk."""
    load_wallets.cache_clear()
    return load_wallets()
