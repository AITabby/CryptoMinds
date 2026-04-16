#!/usr/bin/env python3
"""
CryptoMinds SDK — AI Agent 的链上工具箱

不做决策，只提供四个干净接口：
  discover_skills()     — 发现市场上的 Skill
  purchase_skill()      — 购买 Skill
  run_skill()           — 执行已安装的 Skill
  get_installed_skills() — 查看已安装的 Skill

决策权在调用方 Agent（它有自己的 LLM 大脑）。
CryptoMinds 只是手脚：市场 + 支付 + 执行。
"""
import json
import time
import sys
import os
from datetime import datetime
import requests as req
from pathlib import Path

DIR = str(Path(__file__).parent)

# x402 支付
try:
    from x402_pay import x402_pay, verify_x402_payment, get_bnb_balance
    X402_ENABLED = True
except ImportError:
    X402_ENABLED = False

# 声誉系统
try:
    from agents.agent_reputation import get_reputation_system
    REPUTATION_ENABLED = True
except ImportError:
    REPUTATION_ENABLED = False

# Agent 微服务端点
AGENT_ENDPOINTS = {
    "tiedan": "http://localhost:5001",
    "choudan": "http://localhost:5002",
    "ludan": "http://localhost:5003",
    "four_meme": "http://localhost:5004",
}

# 市场服务端点
MARKET_URL = os.getenv("CRYPTOMINDS_MARKET", "http://localhost:3456")


def get_skill_endpoint(expert_name, skill_name=None):
    """从 services.json 动态获取 Skill 的 endpoint，找不到则回退硬编码"""
    try:
        resp = req.get(f'{MARKET_URL}/api/services', timeout=5)
        if resp.status_code == 200:
            services = resp.json()
            for s in services:
                if s.get('active') and s.get('expert') == expert_name:
                    if skill_name and s.get('name') != skill_name:
                        continue
                    endpoint = s.get('api', {}).get('endpoint', '')
                    if endpoint:
                        return endpoint
    except Exception:
        pass
    # 回退硬编码
    return AGENT_ENDPOINTS.get(expert_name)


def load_wallets():
    with open(f"{DIR}/wallets.json") as f:
        return json.load(f)


# ============================================================
# 支付
# ============================================================

def pay(from_name, to_name, amount, reason):
    """执行 x402 支付，降级到简单转账"""
    if X402_ENABLED:
        success, tx_hash, payment_info = x402_pay(
            from_name=from_name,
            to_name=to_name,
            amount_bnb=amount,
            service_id=f"service-{to_name}",
            description=reason
        )
        if success:
            valid, msg = verify_x402_payment(payment_info)
            if valid:
                _notify_dashboard(from_name, to_name, amount, reason, tx_hash, payment_info)
                return True, tx_hash
        return False, ""
    else:
        import subprocess
        result = subprocess.run(
            ["python3", f"{DIR}/transfer.py", "send", from_name, to_name, str(amount)],
            capture_output=True, text=True
        )
        success = '成功' in result.stdout
        tx_hash = ""
        if success:
            for line in result.stdout.split('\n'):
                if 'bscscan.com/tx/' in line:
                    tx_hash = line.split('bscscan.com/tx/')[-1].strip()
        if success:
            _notify_dashboard(from_name, to_name, amount, reason, tx_hash)
        return success, tx_hash

def _notify_dashboard(from_name, to_name, amount, reason, tx_hash, payment_info=None):
    """支付成功后通知 Dashboard 记录交易"""
    try:
        import urllib.request
        wallets = json.load(open(WALLETS_FILE))
        from_wallet = wallets.get(from_name, {}).get('address', '')
        is_test = payment_info.get('test_mode', True) if payment_info else True
        data = {
            'time': datetime.now().strftime('%H:%M:%S'),
            'from': from_name,
            'fromWallet': from_wallet,
            'to': to_name,
            'amount': amount,
            'reason': reason,
            'tx': tx_hash or f'py-{int(time.time())}',
            'receipt': tx_hash or f'py-{int(time.time())}',
            'verified': '✅ 已验证' if not is_test else '🧪 模拟',
            'route_type': 'direct/bsc/BNB',
        }
        # 如果有真实链上 tx_hash，生成 BSCScan 链接
        if tx_hash and tx_hash.startswith('0x') and not is_test:
            data['bscscan_url'] = f'https://bscscan.com/tx/{tx_hash}'
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f'{MARKET_URL}/api/tx',
            data=body,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
        print(f'   📊 已同步到 Dashboard')
    except Exception as e:
        print(f'   ⚠️ Dashboard 通知失败: {e}')


# ============================================================
# 四个核心 SDK 接口
# ============================================================

def discover_skills(query=None, category=None, framework='generic'):
    """
    发现市场上的 Skill
    
    Args:
        query: 搜索关键词（可选）
        category: 分类过滤（可选）
        framework: Agent 框架，默认 generic 兼容所有
    
    Returns:
        list: 兼容的 Skill 列表
    """
    try:
        resp = req.get(f'{MARKET_URL}/api/market', timeout=10)
        if resp.status_code != 200:
            return []
        
        skills = resp.json()
        
        # 过滤
        compatible = []
        for s in skills:
            if not s.get('active', True):
                continue
            sec = s.get('security', {})
            if sec.get('level') == 'critical':
                continue
            fws = s.get('frameworks', ['generic'])
            if framework in fws or 'generic' in fws:
                # 关键词过滤
                if query:
                    searchable = f"{s.get('name', '')} {s.get('desc', '')} {s.get('expert', '')}".lower()
                    if query.lower() not in searchable:
                        continue
                compatible.append(s)
        
        return compatible
    except Exception as e:
        print(f"  ⚠️ 市场发现失败: {e}")
        return []


def purchase_skill(skill_id, buyer_wallet, buyer_name=None, payment_mode='demo', tx_hash=None):
    """
    购买 Skill
    
    Args:
        skill_id: Skill ID
        buyer_wallet: 买家钱包地址
        buyer_name: 买家名称（可选）
    
    Returns:
        tuple: (success: bool, purchase_info: dict)
    """
    try:
        resp = req.post(f'{MARKET_URL}/api/services/buy', json={
            'serviceId': skill_id,
            'buyerWallet': buyer_wallet,
            'buyerName': buyer_name or '',
            'paymentMode': payment_mode,
            **({'txHash': tx_hash} if tx_hash else {}),
        }, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('ok', False), data.get('purchase', {})
    except Exception as e:
        print(f"  ⚠️ 购买失败: {e}")
    return False, {}


def run_skill(skill_id, expert, task_prompt, buyer_wallet, buyer_name=None, token_address=None):
    """
    执行 Skill — 购买 + 调用一步完成
    
    Args:
        skill_id: Skill ID
        expert: 专家 Agent 名称（如 tiedan/choudan/ludan/four_meme）
        task_prompt: 任务描述
        buyer_wallet: 买家钱包地址
        buyer_name: 买家名称（可选）
        token_address: 代币地址（可选，风控类任务需要）
    
    Returns:
        dict: 执行结果
    """
    # 支付
    ok, purchase = purchase_skill(skill_id, buyer_wallet, buyer_name)
    if ok:
        print(f"  ✅ 购买成功")
    else:
        print(f"  ⚠️ 购买 demo 模式，继续执行...")
    
    # 调用 Agent
    return _call_agent(expert, task_prompt, token_address=token_address)


def get_installed_skills(wallet):
    """
    获取已安装的 Skill 列表
    
    Args:
        wallet: 钱包地址
    
    Returns:
        list: 已安装的 Skill 列表
    """
    try:
        resp = req.get(f'{MARKET_URL}/api/agents/{wallet}/skills', timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('skills', [])
    except Exception:
        pass
    return []


# ============================================================
# 内部：Agent 调用
# ============================================================

def _call_agent(agent_name, task, token_address=None):
    """调用 Agent 服务，网络不可用时尝试本地 runtime"""
    endpoint = get_skill_endpoint(agent_name)
    request_id = f"req-{agent_name}-{int(time.time())}"
    
    # 1. 尝试网络调用（先快速检测端口是否可达）
    if endpoint:
        start = time.time()
        try:
            # 快速检测：1秒连不上就降级，不卡30秒
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            host = parsed.hostname or 'localhost'
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            reachable = sock.connect_ex((host, port)) == 0
            sock.close()
            if not reachable:
                raise ConnectionError(f"{host}:{port} 不可达")
            
            resp = req.post(f"{endpoint}/execute", json={
                "request_id": request_id,
                "task": task,
                "token_address": token_address,
                "timestamp": time.time(),
            }, timeout=15)
            
            duration = time.time() - start
            if resp.status_code == 200:
                result = resp.json()
                _record_reputation(agent_name, True, duration, request_id=request_id)
                return result.get("data", result)
            else:
                _record_reputation(agent_name, False, duration, f"HTTP {resp.status_code}", request_id)
                print(f"  ⚠️ {agent_name} 返回 {resp.status_code}，尝试本地执行")
        except Exception as e:
            duration = time.time() - start
            _record_reputation(agent_name, False, duration, str(e), request_id)
            print(f"  ⚠️ {agent_name} 网络不可用，尝试本地执行")
    
    # 2. 降级：本地 runtime
    try:
        from agent_runtimes import RUNTIMES
        runtime_fn = RUNTIMES.get(agent_name)
        if runtime_fn:
            return runtime_fn(task_description=task, token_address=token_address)
        else:
            return {"error": f"未知 Agent: {agent_name}，且无本地 runtime"}
    except ImportError:
        return {"error": f"Agent {agent_name} 服务不可用，本地 runtime 也未安装"}
    except Exception as e:
        return {"error": f"本地执行失败: {e}"}


def _record_reputation(agent_name, success, response_time, error_message=None, request_id=None):
    """记录声誉数据"""
    if not REPUTATION_ENABLED:
        return
    try:
        rs = get_reputation_system()
        rs.record_transaction(
            agent_name=agent_name,
            success=success,
            response_time=response_time,
            error_message=error_message,
            request_id=request_id,
        )
    except Exception:
        pass


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    """
    SDK 用法演示
    
    使用方法:
      python3 orchestrator.py discover [query]     # 发现市场
      python3 orchestrator.py scan                  # 扫链
      python3 orchestrator.py risk <token_addr>     # 风控
      python3 orchestrator.py installed <wallet>    # 已安装
    """
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"

    if cmd == "discover":
        query = sys.argv[2] if len(sys.argv) > 2 else None
        skills = discover_skills(query=query)
        print(f"发现 {len(skills)} 个 Skill:")
        for s in skills:
            sec = '✅' if s.get('security', {}).get('level') == 'safe' else '⚠️'
            print(f"  {sec} {s['name']} ({s['expert']}) — {s.get('price', 0)} BNB")
        if not skills:
            print("  （市场服务未启动或无可用 Skill）")
        print("\n→ Agent 根据自己的 LLM 判断，决定买哪个、要不要买")

    elif cmd == "scan":
        wallets = load_wallets()
        result = run_skill("tiedan-scan", "tiedan", "扫描 BNB Chain 最新 meme 币",
                          wallets['gangdan']['address'], buyer_name='gangdan')
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "risk":
        token = sys.argv[2] if len(sys.argv) > 2 else None
        wallets = load_wallets()
        result = run_skill("choudan-risk", "choudan", f"分析代币风险",
                          wallets['gangdan']['address'], buyer_name='gangdan', token_address=token)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "installed":
        wallet = sys.argv[2] if len(sys.argv) > 2 else "0xd2f899CE74320AEf9d8f2359183232a554f4C0E1"
        skills = get_installed_skills(wallet)
        print(f"已安装 {len(skills)} 个 Skill")
        for s in skills:
            print(f"  📦 {s}")

    else:
        print("CryptoMinds SDK — Agent 的链上工具箱")
        print()
        print("用法:")
        print("  python3 orchestrator.py discover [query]     # 发现市场")
        print("  python3 orchestrator.py scan                  # 扫链")
        print("  python3 orchestrator.py risk <token_addr>     # 风控")
        print("  python3 orchestrator.py installed <wallet>    # 已安装")
        print()
        print("CryptoMinds 是工具箱，不是大脑。")
        print("Agent 用自己的 LLM 做决策，调用这些接口执行。")
