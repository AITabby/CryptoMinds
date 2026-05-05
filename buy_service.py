#!/usr/bin/env python3
"""示例脚本：买家钱包向卖家钱包支付雇佣费。"""
import json
import sys
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from config import BSC_RPC, BSC_CHAIN_ID, load_wallets, get_wallet_key

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# 钱包信息
wallets = load_wallets()

# 买家钱包
from_wallet = wallets['choudan']
from_addr = from_wallet['address']
from_pk = get_wallet_key('choudan')

# 卖家钱包
to_addr = wallets['gangdan']['address']

# 雇佣费用
amount_bnb = 0.000116

# 检查余额
bal = w3.eth.get_balance(from_addr)
print(f"买家余额: {w3.from_wei(bal, 'ether')} BNB")

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
    'chainId': BSC_CHAIN_ID,
}

# 签名并发送
print(f"\n正在发送交易: 买家 → 卖家 ({amount_bnb} BNB)...")
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
            'from': '买家Agent',
            'fromWallet': from_addr,
            'to': '卖家Agent',
            'amount': amount_bnb,
            'reason': '支付雇佣费',
            'tx': tx_hash.hex(),
            'receipt': tx_hash.hex(),
            'route_type': 'direct/bsc/BNB',
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'http://localhost:3457/api/v1/tx',
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
