#!/usr/bin/env python3
"""
钢蛋自主决策 Demo — 完整闭环（真实交易链路）
1. 启动 web 服务
2. 发现市场（HTTP）
3. 购买 Skill（HTTP + x402/demo）
4. 执行 Skill（Agent runtime）
5. 声誉记录
6. 汇总
"""
import json
import sys
import os
import time
import subprocess
import signal
from pathlib import Path

DIR = str(Path(__file__).parent.parent)
sys.path.insert(0, DIR)

from agents.agent_reputation import get_reputation_system

WALLET = "0xd2f899CE74320AEf9d8f2359183232a554f4C0E1"
MARKET_URL = "http://localhost:3456"
WEB_PROC = None

def think(context):
    print(f"\n  🧠 钢蛋思考: {context}")

def step(num, title):
    print(f"\n{'='*50}")
    print(f"  Step {num}: {title}")
    print(f"{'='*50}")

def start_web_server():
    """启动 web 服务"""
    global WEB_PROC
    # 先检测是否已运行
    import urllib.request
    try:
        urllib.request.urlopen(f"{MARKET_URL}/api/market", timeout=2)
        print("  ℹ️ Web 服务已在运行")
        return True
    except Exception:
        pass
    
    print("  🚀 启动 Web 服务...")
    WEB_PROC = subprocess.Popen(
        ["node", "server.js"],
        cwd=os.path.join(DIR, "web"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PORT": "3456", "CRYPTOMINDS_OFFLINE": "1"},
    )
    # 等服务启动
    for i in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{MARKET_URL}/api/market", timeout=2)
            print(f"  ✅ Web 服务已启动 ({i+1}s)")
            return True
        except Exception:
            continue
    
    print("  ❌ Web 服务启动超时")
    return False

def stop_web_server():
    global WEB_PROC
    if WEB_PROC:
        WEB_PROC.terminate()
        WEB_PROC.wait(timeout=5)
        WEB_PROC = None

def http_get(path):
    import urllib.request
    resp = urllib.request.urlopen(f"{MARKET_URL}{path}", timeout=10)
    return json.loads(resp.read())

def http_post(path, data):
    import urllib.request
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{MARKET_URL}{path}", data=body,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

def main():
    print("🤖 钢蛋 — 自主决策 Demo（完整交易链路）")
    print("="*50)
    print(f"   钱包: {WALLET[:10]}...")
    print(f"   角色: 买家 Agent")
    print()
    
    # 启动服务
    if not start_web_server():
        print("无法启动服务，退出")
        return
    
    try:
        # ── 用户请求 ──
        print("\n👤 用户: 帮我看看有没有值得买的 meme 币")
        
        # ── Step 1: 发现市场（HTTP） ──
        step(1, "发现市场（HTTP GET /api/market）")
        think("用户想找 meme 币，我先搜市场有什么工具")
        
        market = http_get("/api/market")
        services = market if isinstance(market, list) else market.get('services', market.get('data', []))
        print(f"\n  📋 市场上 {len(services)} 个 Skill:")
        for s in services:
            rep = s.get('reputation')
            rep_str = f" | 声誉 {rep['score']:.0f}({rep['grade']})" if rep else ""
            print(f"     • {s.get('name','?')} by {s.get('expert','?')} — {s.get('price',0)} BNB, ⭐{s.get('rating',0)}{rep_str}")
        
        # ── Step 2: 自主判断 ──
        step(2, "自主判断")
        think("扫链 Skill 便宜评分高，先买它发现代币")
        
        scan_skill = next((s for s in services if s['id'] == 'tiedan-scan'), None)
        risk_skill = next((s for s in services if s['id'] == 'choudan-risk'), None)
        
        # ── Step 3: 真实购买扫链 Skill（HTTP POST） ──
        step(3, "购买扫链 Skill（HTTP POST /api/services/buy）")
        if scan_skill:
            print(f"\n  💰 购买: {scan_skill['name']}")
            buy_result = http_post("/api/services/buy", {
                "serviceId": scan_skill['id'],
                "buyerWallet": WALLET,
                "buyerName": "gangdan",
                "paymentMode": "demo",
            })
            ok = buy_result.get('ok', False)
            purchase = buy_result.get('purchase', {})
            payment_mode = purchase.get('payment', {}).get('mode', '?')
            print(f"  {'✅' if ok else '❌'} 购买结果: {payment_mode} 模式, 订单 {purchase.get('id', '?')[:20]}...")
            
            # 执行 runtime
            print(f"  🔧 执行: 调用铁蛋(tiedan) runtime...")
            from agent_runtimes import RUNTIMES
            start = time.time()
            scan_result = RUNTIMES['tiedan'](task_description="扫描 BNB Chain 最新 meme 币")
            duration = time.time() - start
            print(f"  ⏱️ 耗时: {duration:.1f}s")
            
            # 记录声誉
            rs = get_reputation_system()
            rs.record_transaction('tiedan', success=True, response_time=duration)
            
            scanning = scan_result.get('scanning', scan_result)
            hot = scanning.get('hot_tokens', [])
            print(f"\n  📊 扫到 {scanning.get('tokens_scanned', 0)} 个代币:")
            for t in hot[:3]:
                print(f"     • {t.get('symbol','?')}: 24h {t.get('price_change_24h',0):+.1f}%, 流动性 ${t.get('liquidity_usd',0):,.0f}")
            print(f"  🔥 推荐: {scanning.get('recommendation', '暂无')}")
            target_token = hot[0] if hot else {}
        
        # ── Step 4: 自主决策买风控 ──
        step(4, "自主判断 + 购买风控 Skill")
        think("扫到代币了，需要风控验证安全性")
        
        if risk_skill:
            print(f"\n  💰 购买: {risk_skill['name']}")
            buy_result2 = http_post("/api/services/buy", {
                "serviceId": risk_skill['id'],
                "buyerWallet": WALLET,
                "buyerName": "gangdan",
                "paymentMode": "demo",
            })
            ok2 = buy_result2.get('ok', False)
            purchase2 = buy_result2.get('purchase', {})
            print(f"  {'✅' if ok2 else '❌'} 购买结果: {purchase2.get('payment', {}).get('mode', '?')} 模式")
            
            print(f"  🔧 执行: 调用臭蛋(choudan) runtime...")
            token_addr = target_token.get('address')
            start = time.time()
            risk_result = RUNTIMES['choudan'](task_description="分析代币风险", token_address=token_addr)
            duration = time.time() - start
            print(f"  ⏱️ 耗时: {duration:.1f}s")
            
            rs.record_transaction('choudan', success=True, response_time=duration)
            
            risk = risk_result.get('risk', risk_result)
            score = risk.get('score', 0)
            level = risk.get('risk', '?')
            print(f"\n  🔒 {risk.get('symbol','?')} 风控: 评分 {score}/100 ({level}风险)")
            for c in risk.get('checks', [])[:5]:
                status = c.get('status', '?')
                icon = '✅' if '✅' in status else '⚠️' if '⚠️' in status else '❌'
                print(f"     {icon} {c.get('item','?')}: {c.get('detail','')}")
            print(f"  📝 结论: {risk.get('conclusion','?')}")
        
        # ── Step 5: 汇总 ──
        step(5, "汇总报告")
        think("信息收集完毕，给用户结论")
        
        print(f"\n  📋 ─────── 钢蛋最终报告 ───────")
        print(f"  扫链: {scanning.get('recommendation', '暂无')}")
        print(f"  风控: {risk.get('symbol','?')} 评分 {risk.get('score',0)}/100, {risk.get('risk','?')}风险")
        print(f"  建议: {risk.get('conclusion','请自行判断')}")
        print(f"  ────────────────────────────────")
        print(f"\n  🤖 钢蛋: 全程通过 HTTP 交易链路完成")
        print(f"          发现→购买→支付→执行→声誉记录")
        
        # 声誉
        print(f"\n  📊 声誉记录:")
        for name in ['tiedan', 'choudan']:
            rep = rs.get_reputation(name)
            if rep:
                stats = rep.get('statistics', {})
                print(f"     {name}: ⭐{rep.get('reputation_score',0):.1f} ({rep.get('grade','?')}) | {stats.get('total_requests',0)}笔 | 成功率 {stats.get('success_rate',0):.0f}%")
        
        print(f"\n{'='*50}")
        print(f"✅ 完整交易闭环完成")
        print(f"{'='*50}")
    
    finally:
        stop_web_server()

if __name__ == "__main__":
    main()
