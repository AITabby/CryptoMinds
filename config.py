#!/usr/bin/env python3
"""
CryptoMinds 共享配置
所有链上 RPC、合约地址等统一在此管理，避免散落各处
"""

import os
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
