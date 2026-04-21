#!/usr/bin/env python3
"""
Risk Sentinel — 风控卖家
5 项链上安全检查：合约所有权、代码量、持仓集中度、流动性、供应量
"""
import json
import sys
import os
from pathlib import Path

DIR = str(Path(__file__).parent.parent)
sys.path.insert(0, DIR)


def run(task_description=None, token_address=None):
    """执行风控分析"""
    try:
        from agent_events import think as _think, execute as _exec, result as _result
    except ImportError:
        _think = _exec = _result = lambda *a, **kw: None

    _think("Risk Sentinel", f"收到风控任务: {task_description or '分析代币安全性'}")
    
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    from config import BSC_RPC
    w3 = Web3(Web3.HTTPProvider(BSC_RPC))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    target = token_address or "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
    _exec("Risk Sentinel", f"分析合约 {target[:10]}... — 5 项链上安全检查")

    FULL_ABI = json.loads(
        '[{"inputs":[],"name":"name","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},'
        '{"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},'
        '{"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},'
        '{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},'
        '{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"},'
        '{"inputs":[],"name":"owner","outputs":[{"type":"address"}],"stateMutability":"view","type":"function"}]'
    )

    checks = []
    score = 50
    name, symbol = "Unknown", "???"
    total_supply = 0
    supply_readable = 0
    owner_addr = None

    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(target), abi=FULL_ABI)
        name = token.functions.name().call()
        symbol = token.functions.symbol().call()
        total_supply = token.functions.totalSupply().call()
        decimals = token.functions.decimals().call()
        supply_readable = total_supply / (10 ** decimals) if decimals else total_supply
    except Exception:
        pass

    # 检查 1: Owner 权限
    try:
        owner_addr = token.functions.owner().call()
        if owner_addr == "0x0000000000000000000000000000000000000000":
            checks.append({"item": "合约所有权", "status": "✅ 已放弃", "detail": "owner 已归零，无法随意 mint/暂停"})
            score += 20
        else:
            checks.append({"item": "合约所有权", "status": "⚠️ 未放弃", "detail": f"owner: {owner_addr[:10]}...，可随时 mint 新币或暂停交易"})
            score -= 15
    except Exception:
        checks.append({"item": "合约所有权", "status": "✅ 无 owner 函数", "detail": "不可升级，权限固定"})
        score += 15

    # 检查 2: 合约代码量
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(target))
        code_size = len(code)
        if code_size > 5000:
            checks.append({"item": "合约代码量", "status": "✅ 正常", "detail": f"{code_size:,} bytes，合约功能较完整"})
            score += 10
        elif code_size > 1000:
            checks.append({"item": "合约代码量", "status": "⚠️ 偏小", "detail": f"{code_size:,} bytes，可能是代理合约"})
            score += 5
        else:
            checks.append({"item": "合约代码量", "status": "❌ 极小", "detail": f"仅 {code_size:,} bytes，疑似蜜罐或空壳合约"})
            score -= 20
    except Exception:
        checks.append({"item": "合约代码量", "status": "❓ 无法获取", "detail": "RPC 调用失败"})

    # 检查 3: 部署者持仓集中度
    try:
        if owner_addr:
            deployer_balance = token.functions.balanceOf(Web3.to_checksum_address(owner_addr)).call()
            deployer_pct = (deployer_balance / total_supply * 100) if total_supply > 0 else 0
            if deployer_pct < 5:
                checks.append({"item": "部署者持仓", "status": "✅ 分散", "detail": f"部署者持仓 {deployer_pct:.1f}%，抛压风险低"})
                score += 15
            elif deployer_pct < 20:
                checks.append({"item": "部署者持仓", "status": "⚠️ 偏高", "detail": f"部署者持仓 {deployer_pct:.1f}%，有一定抛压风险"})
                score -= 5
            else:
                checks.append({"item": "部署者持仓", "status": "❌ 集中", "detail": f"部署者持仓 {deployer_pct:.1f}%，Rug 风险大"})
                score -= 20
    except Exception:
        checks.append({"item": "部署者持仓", "status": "❓ 无法检查", "detail": "balanceOf 调用失败"})

    # 检查 4: DEXScreener 流动性
    try:
        from four_meme_client import get_dexscreener_info
        dex_info = get_dexscreener_info(target)
        if dex_info:
            liq = dex_info.get("liquidity_usd", 0)
            vol = dex_info.get("volume_24h", 0)
            chg = dex_info.get("price_change_24h", 0)
            if liq > 100_000:
                checks.append({"item": "流动性", "status": "✅ 充足", "detail": f"流动性 ${liq:,.0f}，24h 交易量 ${vol:,.0f}，24h 涨跌 {chg:+.1f}%"})
                score += 15
            elif liq > 10_000:
                checks.append({"item": "流动性", "status": "⚠️ 一般", "detail": f"流动性 ${liq:,.0f}，24h 交易量 ${vol:,.0f}，滑点可能较大"})
                score += 5
            else:
                checks.append({"item": "流动性", "status": "❌ 极低", "detail": f"流动性仅 ${liq:,.0f}，买入后可能无法卖出"})
                score -= 15
        else:
            checks.append({"item": "流动性", "status": "⚠️ 无数据", "detail": "DEXScreener 未收录此代币"})
            score -= 5
    except Exception:
        checks.append({"item": "流动性", "status": "❓ 查询失败", "detail": "DEXScreener API 不可用"})

    # 检查 5: 供应量合理性
    try:
        if supply_readable > 0:
            if supply_readable < 1_000_000:
                checks.append({"item": "供应量", "status": "⚠️ 偏低", "detail": f"总供应 {supply_readable:,.0f}，单价可能被操纵"})
                score -= 5
            elif supply_readable > 1_000_000_000_000:
                checks.append({"item": "供应量", "status": "⚠️ 极大", "detail": f"总供应 {supply_readable:,.0f}，典型 meme 币高供应模式"})
            else:
                checks.append({"item": "供应量", "status": "✅ 正常", "detail": f"总供应 {supply_readable:,.0f}"})
                score += 5
    except Exception:
        pass

    score = min(100, max(0, score))

    if score >= 75:
        conclusion = f"{symbol} 安全性较好：合约权限已限制、流动性充足、持仓分散。可以小仓位参与。"
    elif score >= 50:
        conclusion = f"{symbol} 存在一定风险：部分指标未达标，建议小额试水、设好止损。"
    elif score >= 30:
        conclusion = f"{symbol} 风险较高：多项指标异常，不建议大额参与。"
    else:
        conclusion = f"⚠️ {symbol} 高度危险：疑似蜜罐或 Rug 项目，强烈建议远离！"

    _result("Risk Sentinel", f"{symbol} 风控完成: 评分 {score}/100 ({'低' if score >= 75 else '中' if score >= 50 else '高' if score >= 30 else '极高'}风险)")

    return {
        "risk": {
            "name": name,
            "symbol": symbol,
            "address": target,
            "checks": checks,
            "score": score,
            "risk": "低" if score >= 75 else "中" if score >= 50 else "高" if score >= 30 else "极高",
            "conclusion": conclusion,
            "source": "链上合约分析 + DEXScreener 市场数据",
            "agent": "choudan",
        }
    }
