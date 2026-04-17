#!/usr/bin/env python3
"""购买服务 - 臭蛋购买小钢蛋蛋的服务"""
import json
import sys
import os
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

sys.path.insert(0, '/Users/aitabby/projects/cryptominds')
from config import BSC_RPC

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# 钱包信息
WALLETS_FILE = '/Users/aitabby/projects/cryptominds/wallets.json'
with open(WALLETS_FILE) as f:
    wallets = json.load(f)

# 臭蛋钱包
from_wallet = wallets['choudan']
from_addr = from_wallet['address']
from_pk = from_wallet['private_key']

# 钢蛋钱包（小钢蛋蛋的服务提供者）
to_addr = wallets['gangdan']['address']

# 服务价格
amount_bnb = 0.000116  # 链上巨鲸查询服务价格

# 检查余额
bal = w3.eth.get_balance(from_addr)
print(f"臭蛋余额: {w3.from_wei(bal, 'ether')} BNB")

if bal < w3.to_wei(amount_bnb, 'ether'):
    print(f"余额不足!")
    sys.exit(1)

# 构建交易
nonce = w3.eth.get_transaction_count(from_addr)
gas_price = w3.eth.gas_price

tx = {
    'nonce': nonce,
    'to': to_addr,
    'value': w3.to_wei(amount_bnb, 'ether'),
    'gas': 21000,
    'gasPrice': gas_price,
    'chainId': 56,  # BSC Mainnet
}

# 签名并发送
print(f"\n正在发送交易: 臭蛋 → 钢蛋 ({amount_bnb} BNB)...")
signed = w3.eth.account.sign_transaction(tx, from_pk)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

print(f"交易已发送: {tx_hash.hex()}")
print(f"等待确认...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

if receipt['status'] == 1:
    print(f"\n✅ 购买成功!")
    print(f"   TX: https://bscscan.com/tx/{tx_hash.hex()}")
    print(f"   Gas used: {receipt['gasUsed']}")
    
    # 通知 Dashboard
    try:
        import urllib.request
        data = json.dumps({
            'from': '臭蛋',
            'fromWallet': from_addr,
            'to': '钢蛋',
            'amount': amount_bnb,
            'reason': '购买服务: 链上巨鲸查询',
            'tx': tx_hash.hex(),
            'receipt': tx_hash.hex(),
            'route_type': 'direct/bsc/BNB',
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'http://localhost:3456/api/tx',
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req)
        print("   已同步到 Dashboard")
    except Exception as e:
        print(f"   Dashboard 同步失败: {e}")
else:
    print(f"\n❌ 交易失败")
    sys.exit(1)
