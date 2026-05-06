#!/usr/bin/env python3
"""
CryptoMinds 共享配置
所有链上 RPC、合约地址等统一在此管理，避免散落各处
"""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WALLETS_FILE = PROJECT_ROOT / "wallets.json"

# ── BSC RPC ──────────────────────────────────────────────
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org/")
BSC_CHAIN_ID = int(os.getenv("BSC_CHAIN_ID", "56"))
BSC_RPC_FALLBACKS = os.getenv("BSC_RPC_FALLBACKS", "https://bsc-dataseed2.binance.org,https://bsc-dataseed3.binance.org,https://bsc-dataseed4.binance.org").split(",")
RPC_TIMEOUT_SECONDS = int(os.getenv("RPC_TIMEOUT_SECONDS", "5"))
RPC_MAX_RETRIES = int(os.getenv("RPC_MAX_RETRIES", "3"))

# ── PancakeSwap V2 Router ───────────────────────────────
PANCAKE_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# ── BSC USDC (替代 USDT，dataseed 查不到 USDT code) ─────
BSC_USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
BSC_USDC_DECIMALS = 18

# ── 买币保护参数 ─────────────────────────────────────────
# 默认接受 5% 滑点，生产环境可以按部署需要继续收紧
DEFAULT_SLIPPAGE_BPS = int(os.getenv("DEFAULT_SLIPPAGE_BPS", "500"))


# ── 集中式钱包加载 ──────────────────────────────────────────

def load_wallets() -> dict:
    """Load wallets from env vars (priority) then wallets.json. Not cached."""
    result = {}
    # First: load from WALLET_KEY_{NAME} env vars
    for env_key, value in os.environ.items():
        if env_key.startswith("WALLET_KEY_"):
            name = env_key[len("WALLET_KEY_"):].lower()
            pk = value
            if pk and not pk.startswith("0x"):
                pk = "0x" + pk
            # Derive address from env var if WALLET_ADDR_{NAME} is set, else empty
            addr = os.getenv(f"WALLET_ADDR_{name.upper()}", "")
            result[name] = {"address": addr, "private_key": pk}
    # Second: load from wallets.json (env vars override same names)
    if WALLETS_FILE.exists():
        raw = json.loads(WALLETS_FILE.read_text())
        for name, info in raw.items():
            if name in result:
                continue  # env var wins
            pk = info.get("private_key") or info.get("privateKey") or info.get("key") or ""
            if pk and not pk.startswith("0x"):
                pk = "0x" + pk
            result[name] = {
                "address": info.get("address", ""),
                "private_key": pk,
            }
    return result


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
    """Re-read wallets from disk (no cache to clear — always fresh)."""
    return load_wallets()


# ── RPC helper with timeout + retry + fallback ──────────────────

def create_web3_with_retry(rpc_url=None, timeout=None, max_retries=None):
    """Create Web3 instance with timeout and fallback RPC endpoints.

    Tries primary RPC first, then fallbacks on failure.
    Returns (w3, used_url) or raises ConnectionError after all attempts fail.
    """
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    rpc_url = rpc_url or BSC_RPC
    timeout = timeout or RPC_TIMEOUT_SECONDS
    max_retries = max_retries or RPC_MAX_RETRIES

    # Candidate URLs: primary first, then fallbacks
    candidates = [rpc_url] + [u.strip() for u in BSC_RPC_FALLBACKS if u.strip()]

    for url in candidates:
        for attempt in range(max_retries):
            try:
                provider = Web3.HTTPProvider(url, request_kwargs={"timeout": timeout})
                w3 = Web3(provider)
                # BSC/Polygon need POA middleware
                if "bsc" in url.lower() or "polygon" in url.lower():
                    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                # Verify connection
                if w3.is_connected():
                    return w3, url
            except Exception:
                pass
    raise ConnectionError(f"All RPC endpoints failed after {max_retries} retries: {candidates}")
