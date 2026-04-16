#!/usr/bin/env python3
"""
Four.meme 数据客户端（链上真实版）
从 PancakeSwap Factory + DEXScreener 获取 Four.meme 上线的最新代币数据
供 CryptoMinds Agent 分析使用
"""

import json
import time
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

# ============================================================
# 链上数据源（无需 API key）
# ============================================================

from config import BSC_RPC
PANCAKE_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
ERC20_ABI = json.loads('[{"inputs":[],"name":"name","outputs":[{"type":"string"}],"type":"function"},{"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"type":"function"},{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"type":"function"},{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"type":"function"}]')
FACTORY_ABI = json.loads('[{"inputs":[{"type":"uint256"}],"name":"allPairs","outputs":[{"type":"address"}],"type":"function"},{"inputs":[],"name":"allPairsLength","outputs":[{"type":"uint256"}],"type":"function"},{"inputs":[{"name":"tokenA","type":"address"},{"name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"type":"address"}],"type":"function"}]')
PAIR_ABI = json.loads('[{"inputs":[],"name":"token0","outputs":[{"type":"address"}],"type":"function"},{"inputs":[],"name":"token1","outputs":[{"type":"address"}],"type":"function"},{"inputs":[],"name":"getReserves","outputs":[{"type":"uint112"},{"type":"uint112"},{"type":"uint32"}],"type":"function"}]')


def rpc_call(method: str, params: list) -> dict:
    """EVM JSON-RPC 调用"""
    try:
        resp = requests.post(BSC_RPC, json={
            "jsonrpc": "2.0", "method": method, "params": params, "id": 1
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def get_latest_pancake_pairs(count: int = 20) -> List[Dict]:
    """从 PancakeSwap Factory 获取最新创建的交易对"""
    try:
        # allPairsLength
        result = rpc_call("eth_call", [{
            "to": PANCAKE_FACTORY,
            "data": "0x574f2ba3"  # allPairsLength()
        }, "latest"])
        if "result" not in result:
            return []
        total = int(result["result"], 16)

        pairs = []
        for i in range(total - 1, max(0, total - count - 1), -1):
            # allPairs(uint256)
            idx_hex = hex(i)[2:].zfill(64)
            data = "0x1e3dd18b" + idx_hex  # allPairs(uint256)
            r = rpc_call("eth_call", [{"to": PANCAKE_FACTORY, "data": data}, "latest"])
            if "result" in r and r["result"] != "0x" + "0" * 64:
                pair_addr = "0x" + r["result"][26:].lower()
                pairs.append({"index": i, "address": pair_addr})
        return pairs
    except Exception:
        return []


def get_pair_tokens(pair_addr: str) -> Optional[Dict]:
    """获取交易对的两个代币地址"""
    try:
        # token0()
        r0 = rpc_call("eth_call", [{"to": pair_addr, "data": "0x0dfe1681"}, "latest"])
        # token1()
        r1 = rpc_call("eth_call", [{"to": pair_addr, "data": "0xd21220a7"}, "latest"])
        if "result" in r0 and "result" in r1:
            return {
                "token0": "0x" + r0["result"][26:].lower(),
                "token1": "0x" + r1["result"][26:].lower(),
            }
    except Exception:
        pass
    return None


def get_token_info(token_addr: str) -> Optional[Dict]:
    """获取 ERC20 代币基本信息"""
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        token = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)

        name = token.functions.name().call()
        symbol = token.functions.symbol().call()
        decimals = token.functions.decimals().call()
        total_supply = token.functions.totalSupply().call()

        return {
            "address": token_addr,
            "name": name,
            "symbol": symbol,
            "decimals": decimals,
            "total_supply": total_supply / (10 ** decimals),
        }
    except Exception:
        return None


def get_pair_reserves(pair_addr: str) -> Optional[Dict]:
    """获取交易对的储备量"""
    try:
        # getReserves()
        r = rpc_call("eth_call", [{"to": pair_addr, "data": "0x0902f1ac"}, "latest"])
        if "result" in r and r["result"] != "0x":
            hex_str = r["result"][2:]
            r0 = int(hex_str[0:64], 16)
            r1 = int(hex_str[64:128], 16)
            ts = int(hex_str[128:192], 16)
            return {"reserve0": r0, "reserve1": r1, "timestamp": ts}
    except Exception:
        pass
    return None


# ============================================================
# DEXScreener API（免费，真实价格数据）
# ============================================================

def get_dexscreener_info(token_addr: str) -> Optional[Dict]:
    """从 DEXScreener 获取代币的市场数据"""
    try:
        resp = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                # 取第一个（流动性最大的）
                p = pairs[0]
                return {
                    "price_usd": float(p.get("priceUsd", 0)),
                    "price_native": float(p.get("priceNative", 0)),
                    "volume_24h": float(p.get("volume", {}).get("h24", 0)),
                    "market_cap": float(p.get("fdv", 0)),
                    "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0)),
                    "price_change_24h": float(p.get("priceChange", {}).get("h24", 0)),
                    "txns_24h": p.get("txns", {}).get("h24", {}),
                    "pair_name": p.get("baseToken", {}).get("symbol", "") + "/" + p.get("quoteToken", {}).get("symbol", ""),
                    "dex": p.get("dexId", ""),
                }
    except Exception:
        pass
    return None


# ============================================================
# 主接口
# ============================================================

def scan_four_meme_tokens(count: int = 10) -> List[Dict]:
    """
    扫描 Four.meme 上线的最新代币
    通过 PancakeSwap 最新交易对 + DEXScreener 获取真实数据
    """
    known_stable = {
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
        "0xe9e7cea3dedca5984780bafc599bd69add087d56",  # BUSD
        "0x55d398326f99059ff775485246999027b3197955",  # USDT
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
        "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",  # CAKE
        "0x2170ed0880ac9a755fd29b2688956bd959f933f8",  # ETH
    }

    WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"

    pairs = get_latest_pancake_pairs(count * 3)  # 多取一些，过滤掉稳定币对
    tokens = []
    seen = set()

    for pair in pairs:
        if len(tokens) >= count:
            break

        pair_tokens = get_pair_tokens(pair["address"])
        if not pair_tokens:
            continue

        # 找出非稳定币的那个代币
        t0 = pair_tokens["token0"]
        t1 = pair_tokens["token1"]

        if t0 in known_stable and t1 not in known_stable:
            new_token_addr = t1
            quote_token = t0
        elif t1 in known_stable and t0 not in known_stable:
            new_token_addr = t0
            quote_token = t1
        else:
            continue

        if new_token_addr in seen:
            continue
        seen.add(new_token_addr)

        # 获取代币信息
        info = get_token_info(new_token_addr)
        if not info:
            continue

        # 从 DEXScreener 获取市场数据
        dex_info = get_dexscreener_info(new_token_addr)

        token_data = {
            "pair_index": pair["index"],
            "pair_address": pair["address"],
            "address": new_token_addr,
            "name": info["name"],
            "symbol": info["symbol"],
            "decimals": info["decimals"],
            "total_supply": info["total_supply"],
            "quote_token": quote_token,
            "source": "链上实时查询",
        }

        if dex_info:
            token_data.update({
                "price_usd": dex_info["price_usd"],
                "volume_24h": dex_info["volume_24h"],
                "market_cap": dex_info["market_cap"],
                "liquidity_usd": dex_info["liquidity_usd"],
                "price_change_24h": dex_info["price_change_24h"],
                "pair_name": dex_info["pair_name"],
            })
        else:
            # 用链上储备量估算
            reserves = get_pair_reserves(pair["address"])
            if reserves:
                token_data["reserves"] = reserves

        tokens.append(token_data)

    return tokens


def get_latest_meme_coins(chain: str = "bsc", limit: int = 5) -> List[Dict]:
    """兼容接口：供 orchestrator.py 调用"""
    tokens = scan_four_meme_tokens(count=limit)
    # 转换为 orchestrator 期望的格式
    result = []
    for t in tokens:
        result.append({
            "id": f"fourmeme-{t['pair_index']}",
            "name": t["name"],
            "symbol": t["symbol"],
            "address": t["address"],
            "price": t.get("price_usd", 0),
            "market_cap": t.get("market_cap", 0),
            "volume_24h": t.get("volume_24h", 0),
            "holders": 0,  # 链上查 holders 较慢，DEXScreener 不提供
            "created_at": int(time.time()),
            "description": f"{t['name']} ({t['symbol']}) — {t.get('pair_name', 'BSC')} 最新上线",
        })
    return result


if __name__ == "__main__":
    print("🔍 扫描 Four.meme 最新代币（链上实时数据）...")
    tokens = scan_four_meme_tokens(count=5)
    for t in tokens:
        price = t.get("price_usd", 0)
        mcap = t.get("market_cap", 0)
        vol = t.get("volume_24h", 0)
        print(f"  {t['symbol']:10s} | ${price:<14.8f} | MCap: ${mcap:>12,.0f} | 24h Vol: ${vol:>12,.0f} | {t.get('pair_name','')}")
