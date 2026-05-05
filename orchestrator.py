#!/usr/bin/env python3
"""
CryptoMinds v2 Orchestrator — 买家 Agent 自动交易流程

核心流程：
  1. 买家给 Agent 发消息："拿 1 BNB 帮我买币"
  2. Agent 搜索卖家市场，按权重/评分/销量选卖家
  3. Agent 直接付款（x402 或 BSC 链上转账）
  4. 平台创建订单，通知卖家 Agent
  5. 卖家 Agent 自动买币 + 转币到买家钱包
  6. 平台验证履约，更新权重和评分

人类只需要：注册 + 发消息
"""
import json
import time
import sys
import os
from datetime import datetime
from pathlib import Path

import requests as req

from config import BSC_CHAIN_ID, load_wallets, get_wallet_key

DIR = str(Path(__file__).parent)
MARKET_URL = os.getenv("CRYPTOMINDS_MARKET", "http://localhost:3457")

# x402 支付
try:
    from x402_pay import x402_pay, verify_x402_payment, get_bnb_balance
    X402_ENABLED = True
except ImportError:
    X402_ENABLED = False


# ============================================================
# 第一步：搜索卖家
# ============================================================

def search_sellers(query=None, sort_by='weight', limit=10):
    """
    搜索卖家市场的卖家
    
    Args:
        query: 搜索关键词（可选）
        sort_by: 排序方式 weight/sales/price
        limit: 返回数量
    
    Returns:
        list: 卖家列表，按权重排序
    """
    try:
        resp = req.get(f'{MARKET_URL}/api/v1/sellers', timeout=10)
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        sellers = data.get('sellers', [])
        
        # 过滤
        if query:
            q = query.lower()
            sellers = [s for s in sellers if 
                q in s.get('name', '').lower() or 
                q in s.get('desc', '').lower() or
                q in s.get('strategy', '').lower()
            ]
        
        # 排序
        if sort_by == 'weight':
            sellers.sort(key=lambda s: (s.get('deposit', 0) * s.get('totalOrders', 0) * s.get('rating', 1)), reverse=True)
        elif sort_by == 'sales':
            sellers.sort(key=lambda s: s.get('totalOrders', 0), reverse=True)
        elif sort_by == 'price':
            sellers.sort(key=lambda s: s.get('feeRate', 999))
        elif sort_by == 'rating':
            sellers.sort(key=lambda s: s.get('rating', 0), reverse=True)
        
        return sellers[:limit]
    except Exception as e:
        print(f"⚠️ 搜索卖家失败: {e}")
        return []


# ============================================================
# 第二步：选择卖家（Agent 自主决策）
# ============================================================

def pick_seller(sellers, amount_bnb):
    """
    Agent 根据权重/评分/可接单额度自主选择卖家
    
    规则：
      - 可接单额度必须 >= 买家下单金额
      - 加权随机选择，权重高的卖家概率大但不垄断
    
    Returns:
        dict: 选中的卖家，或 None
    """
    import random
    
    eligible = []
    for s in sellers:
        deposit = s.get('deposit', 0)
        active_amount = s.get('activeOrders', 0) * s.get('feeRate', 0.005)
        quota = deposit - active_amount
        if quota >= amount_bnb and quota > 0:
            s['_quota'] = quota
            s['_weight'] = deposit * max(s.get('totalOrders', 1), 1) * s.get('rating', 1)
            eligible.append(s)
    
    if not eligible:
        return None
    
    # 加权随机选择，避免单卖家垄断
    weights = [s.get('_weight', 1) for s in eligible]
    return random.choices(eligible, weights=weights, k=1)[0]


# ============================================================
# 第三步：付款（直接转账，不走担保合约）
# ============================================================

def pay_seller(buyer_name, seller_wallet, amount_bnb, service_id):
    """
    买家 Agent 直接付款给卖家
    
    支持 x402 或 BSC 链上转账
    
    Returns:
        tuple: (success, tx_hash)
    """
    wallets = load_wallets()
    buyer_info = wallets.get(buyer_name)
    if not buyer_info:
        print(f"⚠️ 未知买家: {buyer_name}")
        return False, ""
    
    if X402_ENABLED:
        wallets = load_wallets()
        # 找到卖家名称
        seller_name = None
        for name, info in wallets.items():
            if info.get('address', '').lower() == seller_wallet.lower():
                seller_name = name
                break
        if not seller_name:
            seller_name = seller_wallet[:10]
        
        success, tx_hash, payment_info = x402_pay(
            from_name=buyer_name,
            to_name=seller_name,
            amount_bnb=amount_bnb,
            service_id=service_id,
            description=f"CryptoMinds v2 买家付款"
        )
        if success:
            return True, tx_hash
    
    # 降级：BSC 直接转账
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed1.binance.org'))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        buyer_key = get_wallet_key(buyer_name)
        if not buyer_key:
            print(f"⚠️ 找不到 {buyer_name} 的私钥")
            return False, ""
        
        account = w3.eth.account.from_key(buyer_key)
        nonce = w3.eth.get_transaction_count(account.address)
        tx = {
            'from': account.address,
            'to': Web3.to_checksum_address(seller_wallet),
            'value': w3.to_wei(amount_bnb, 'ether'),
            'gas': 25000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': BSC_CHAIN_ID,
        }
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
        print(f"✅ BSC 转账成功: {tx_hash}")
        return True, tx_hash
    except Exception as e:
        print(f"⚠️ BSC 转账失败: {e}")
        # 不再生成假 txHash，转账失败就是失败
        return False, ""


# ============================================================
# 第四步：创建订单
# ============================================================

def create_order(buyer_wallet, buyer_name, seller_wallet, amount_bnb, tx_hash):
    """
    平台记录订单
    
    Returns:
        dict: 订单信息
    """
    try:
        resp = req.post(f'{MARKET_URL}/api/v1/orders/create', json={
            'buyerWallet': buyer_wallet,
            'buyerName': buyer_name,
            'sellerWallet': seller_wallet,
            'amount': amount_bnb,
            'txHash': tx_hash,
            'paymentMode': 'direct',
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('ok'):
                return data.get('order', {})
            else:
                print(f"⚠️ 创建订单失败: {data.get('error')}")
    except Exception as e:
        print(f"⚠️ 创建订单失败: {e}")
    return None


# ============================================================
# 第五步：通知卖家 Agent 执行（平台调用）
# ============================================================

def notify_seller_execute(order_id, seller_wallet, buyer_wallet, amount_bnb):
    """
    通知卖家 Agent 执行买币+转币
    
    平台统一提供执行能力，卖家不需要自己部署
    
    Returns:
        dict: 执行结果 { buy_tx, transfer_tx, token_address, token_amount }
    """
    try:
        resp = req.post(f'{MARKET_URL}/api/v1/orders/{order_id}/execute', json={
            'sellerWallet': seller_wallet,
            'buyerWallet': buyer_wallet,
            'amount': amount_bnb,
        }, timeout=60)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"⚠️ 通知执行失败: {e}")
    return None


# ============================================================
# 一键完整流程：买家 Agent 入口
# ============================================================

def buy_tokens(buyer_name, amount_bnb, query=None):
    """
    买家 Agent 完整流程
    
    1. 搜索卖家
    2. 选择卖家
    3. 付款
    4. 创建订单
    5. 卖家执行买币+转币
    
    Args:
        buyer_name: 买家名称（如 gangdan）
        amount_bnb: 下单金额（BNB）
        query: 搜索关键词（可选）
    
    Returns:
        dict: 执行结果
    """
    print(f"\n🚀 买家 Agent [{buyer_name}] 启动：拿 {amount_bnb} BNB 买币")
    print("=" * 50)
    
    wallets = load_wallets()
    buyer_info = wallets.get(buyer_name)
    if not buyer_info:
        return {"error": f"未知买家: {buyer_name}"}
    
    buyer_wallet = buyer_info['address']
    
    # 1. 搜索卖家
    print(f"\n🔍 第一步：搜索卖家市场...")
    sellers = search_sellers(query=query)
    if not sellers:
        return {"error": "没有可用的卖家"}
    
    print(f"   找到 {len(sellers)} 个卖家:")
    for s in sellers:
        print(f"   • {s['name']} — 押金 {s.get('deposit',0)} BNB | 评分 {s.get('rating','--')} | 销量 {s.get('totalOrders',0)}")
    
    # 2. 选择卖家
    print(f"\n🎯 第二步：选择最优卖家...")
    seller = pick_seller(sellers, amount_bnb)
    if not seller:
        return {"error": f"没有可接单额度 >= {amount_bnb} BNB 的卖家"}
    
    print(f"   ✅ 选中: {seller['name']} (额度 {seller.get('_quota', 0):.4f} BNB)")
    
    # 3. 付款
    print(f"\n💰 第三步：付款 {amount_bnb} BNB...")
    service_id = f"{seller['name']}-{int(time.time())}"
    success, tx_hash = pay_seller(buyer_name, seller['wallet'], amount_bnb, service_id)
    if not success:
        return {"error": "付款失败"}
    
    print(f"   ✅ 付款成功: {tx_hash[:16]}...")
    
    # 4. 创建订单
    print(f"\n📋 第四步：创建订单...")
    order = create_order(buyer_wallet, buyer_name, seller['wallet'], amount_bnb, tx_hash)
    if not order:
        print(f"   ⚠️ 订单创建失败，但付款已完成")
        order = {'id': f'order-{int(time.time())}'}
    
    print(f"   ✅ 订单号: {order.get('id', '--')}")
    
    # 5. 通知卖家执行
    print(f"\n🤖 第五步：卖家 Agent 执行买币+转币...")
    result = notify_seller_execute(order.get('id'), seller['wallet'], buyer_wallet, amount_bnb)
    
    if result and result.get('ok'):
        print(f"   ✅ 执行完成!")
        print(f"   📌 买币 TX: {result.get('buy_tx', '--')[:16]}...")
        print(f"   📌 转币 TX: {result.get('transfer_tx', '--')[:16]}...")
        print(f"   📌 代币: {result.get('token_address', '--')}")
        print(f"   📌 数量: {result.get('token_amount', '--')}")
        # 确认订单完成
        try:
            req.post(f'{MARKET_URL}/api/v1/orders/{order.get("id")}/confirm', json={
                'status': 'completed',
                'tokenAddress': result.get('token_address', ''),
                'tokenAmount': result.get('token_amount', ''),
            }, timeout=10)
        except:
            pass
    else:
        print(f"   ⏳ 卖家 Agent 正在执行中，请等待...")
    
    print(f"\n{'=' * 50}")
    print(f"🎉 流程结束！买家 [{buyer_name}] 的币将发回钱包")
    
    return {
        "ok": True,
        "seller": seller['name'],
        "amount": amount_bnb,
        "tx_hash": tx_hash,
        "order_id": order.get('id'),
        "execute_result": result,
    }


# ============================================================
# 查询
# ============================================================

def get_my_orders(buyer_wallet):
    """查询买家的订单列表"""
    try:
        resp = req.get(f'{MARKET_URL}/api/v1/my-orders?wallet={buyer_wallet}', timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('orders', [])
    except Exception:
        pass
    return []


def get_my_balance(buyer_name):
    """查询买家 BNB 余额"""
    wallets = load_wallets()
    info = wallets.get(buyer_name)
    if not info:
        return 0
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed1.binance.org'))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        balance = w3.eth.get_balance(info['address'])
        return float(w3.from_wei(balance, 'ether'))
    except:
        return 0


# ============================================================
# Legacy SDK compatibility
# ============================================================

def discover_skills(query=None, limit=10):
    """兼容旧版测试/SDK：技能发现映射到卖家市场搜索。"""
    return search_sellers(query=query, limit=limit)


def purchase_skill(buyer_name, seller_wallet=None, amount_bnb=0.001, query=None):
    """兼容旧版测试/SDK：购买技能映射到 v2 买币订单流程。"""
    if seller_wallet:
        query = query or seller_wallet
    return buy_tokens(buyer_name, amount_bnb, query=query)


def run_skill(skill_id=None, task_description=None, token_address=None):
    """兼容旧版测试/SDK：按 runtime 名称执行本地 Agent 能力。"""
    if not skill_id:
        raise ValueError("skill_id is required")
    try:
        from agent_runtimes import RUNTIMES
    except ImportError as exc:
        raise RuntimeError("agent_runtimes unavailable") from exc
    runtime = RUNTIMES.get(skill_id)
    if not runtime:
        raise ValueError(f"unknown skill_id: {skill_id}")
    return runtime(task_description=task_description, token_address=token_address)


def get_installed_skills():
    """兼容旧版测试/SDK：返回当前可用 runtime 名称。"""
    try:
        from agent_runtimes import RUNTIMES
        return list(RUNTIMES.keys())
    except ImportError:
        return []


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if cmd == "buy":
        # python3 orchestrator.py buy gangdan 0.01
        buyer = sys.argv[2] if len(sys.argv) > 2 else "gangdan"
        amount = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
        query = sys.argv[4] if len(sys.argv) > 4 else None
        result = buy_tokens(buyer, amount, query)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif cmd == "search":
        # python3 orchestrator.py search [query]
        query = sys.argv[2] if len(sys.argv) > 2 else None
        sellers = search_sellers(query)
        print(f"找到 {len(sellers)} 个卖家:")
        for s in sellers:
            q = s.get('_quota', s.get('deposit', 0))
            print(f"  • {s['name']} | 押金 {s.get('deposit',0)} BNB | 评分 {s.get('rating','--')} | 销量 {s.get('totalOrders',0)} | 额度 {q:.4f}")
    
    elif cmd == "orders":
        # python3 orchestrator.py orders gangdan
        buyer = sys.argv[2] if len(sys.argv) > 2 else "gangdan"
        wallets = load_wallets()
        orders = get_my_orders(wallets.get(buyer, {}).get('address', ''))
        print(f"共 {len(orders)} 笔订单:")
        for o in orders:
            print(f"  • {o.get('serviceName','--')} | {o.get('price',0)} BNB | {o.get('status','--')}")
    
    elif cmd == "balance":
        buyer = sys.argv[2] if len(sys.argv) > 2 else "gangdan"
        bal = get_my_balance(buyer)
        print(f"{buyer} 余额: {bal:.4f} BNB")
    
    else:
        print("CryptoMinds v2 — 买家 Agent 自动交易")
        print()
        print("用法:")
        print("  python3 orchestrator.py buy <买家> <金额> [关键词]   # 一键买币")
        print("  python3 orchestrator.py search [关键词]              # 搜索卖家")
        print("  python3 orchestrator.py orders <买家>               # 查看订单")
        print("  python3 orchestrator.py balance <买家>              # 查看余额")
        print()
        print("搭场子，不管钱，Agent 自己玩。")
