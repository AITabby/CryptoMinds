#!/usr/bin/env python3
"""CryptoMinds - Agent 间转账工具"""
import json
import sys
import os
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# BSC 主网 RPC
from config import BSC_RPC

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
assert w3.is_connected(), "无法连接 BNB Chain"

WALLETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallets.json")

def load_wallets():
    with open(WALLETS_FILE) as f:
        return json.load(f)

def get_balance(name):
    wallets = load_wallets()
    if name not in wallets:
        print(f"未知 agent: {name}")
        return
    addr = wallets[name]["address"]
    bal = w3.eth.get_balance(addr)
    bnb = w3.from_wei(bal, 'ether')
    print(f"{name} ({addr}): {bnb} BNB")
    return float(bnb)

def get_all_balances():
    wallets = load_wallets()
    for name in wallets:
        addr = wallets[name]["address"]
        bal = w3.eth.get_balance(addr)
        bnb = w3.from_wei(bal, 'ether')
        print(f"  {name}: {bnb} BNB")

def transfer(from_name, to_name, amount_bnb):
    """从一个 agent 转账给另一个 agent"""
    wallets = load_wallets()
    
    if from_name not in wallets:
        print(f"未知发送方: {from_name}")
        return
    if to_name not in wallets:
        print(f"未知接收方: {to_name}")
        return
    
    from_wallet = wallets[from_name]
    to_addr = wallets[to_name]["address"]
    
    # 检查余额
    bal = w3.eth.get_balance(from_wallet["address"])
    bnb_amount = w3.to_wei(amount_bnb, 'ether')
    if bal < bnb_amount:
        print(f"余额不足: {from_name} 只有 {w3.from_wei(bal, 'ether')} BNB")
        return
    
    # 构建交易
    nonce = w3.eth.get_transaction_count(from_wallet["address"])
    tx = {
        'nonce': nonce,
        'to': to_addr,
        'value': bnb_amount,
        'gas': 21000,
        'gasPrice': w3.eth.gas_price,  # 动态获取 gas price
        'chainId': 56,  # BSC Mainnet
    }
    
    # 签名并发送
    signed = w3.eth.account.sign_transaction(tx, from_wallet['private_key'])
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"✅ {from_name} → {to_name}: {amount_bnb} BNB")
    print(f"   TX Hash: https://bscscan.com/tx/{tx_hash.hex()}")
    print(f"   状态: {'成功' if receipt['status'] == 1 else '失败'}")
    
    # 自动同步到 Dashboard
    _notify_dashboard(from_name, to_name, amount_bnb, '链上支付', tx_hash.hex())

def _notify_dashboard(from_name, to_name, amount, reason, tx_hash):
    """转账成功后自动通知 Dashboard"""
    try:
        import urllib.request
        wallets = load_wallets()
        from_wallet = wallets.get(from_name, {}).get('address', '')
        data = json.dumps({
            'from': from_name,
            'fromWallet': from_wallet,
            'to': to_name,
            'amount': amount,
            'reason': reason,
            'tx': tx_hash,
            'receipt': tx_hash,
            'route_type': 'direct/bsc/BNB',
            'verified': '✅ 已验证',
        }).encode()
        req = urllib.request.Request(
            'http://localhost:3457/api/tx',
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5)
        print(f'   📊 已同步到 Dashboard')
    except Exception as e:
        print(f'   ⚠️ Dashboard 通知失败: {e}')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 transfer.py balances              # 查看所有余额")
        print("  python3 transfer.py balance <agent>       # 查看单个余额")
        print("  python3 transfer.py send <from> <to> <amount>  # 转账")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "balances":
        get_all_balances()
    elif cmd == "balance":
        get_balance(sys.argv[2])
    elif cmd == "send":
        transfer(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    else:
        print(f"未知命令: {cmd}")
