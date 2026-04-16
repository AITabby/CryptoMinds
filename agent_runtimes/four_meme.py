#!/usr/bin/env python3
"""
Four.meme 分析专家
获取最新 Four.meme 项目并分析
"""
import json
import time
import sys
import os
from pathlib import Path

DIR = str(Path(__file__).parent.parent)
sys.path.insert(0, DIR)


def run(task_description=None, token_address=None):
    """执行 Four.meme 项目分析"""
    try:
        from four_meme_client import scan_four_meme_tokens
        tokens = scan_four_meme_tokens(count=5)
    except Exception as e:
        return {"four_meme_analysis": {"error": str(e)}}

    analyzed = []
    for t in tokens:
        analyzed.append({
            "name": t.get("name", "Unknown"),
            "symbol": t.get("symbol", "???"),
            "address": t.get("address", ""),
            "price_usd": t.get("price_usd", 0),
            "market_cap": t.get("market_cap", 0),
            "volume_24h": t.get("volume_24h", 0),
            "pair_name": t.get("pair_name", ""),
            "source": t.get("source", "链上查询"),
        })

    return {
        "four_meme_analysis": {
            "tokens": analyzed,
            "count": len(analyzed),
            "source": "PancakeSwap + DEXScreener 链上数据",
            "agent": "four_meme",
            "timestamp": int(time.time()),
        }
    }
