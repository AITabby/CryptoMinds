#!/usr/bin/env python3
"""BNB 转账脚本"""
import sys, json
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from config import BSC_RPC, WALLETS_FILE

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

def transfer_bnb(from_name, to_addr, amount):
    """从 from_name 钱包转 BNB 到 to_addr"""
    wallets = json.load(open(WALLETS_FILE))
    if from_name not in wallets:
        return {"ok": False, "error": f"钱包 {from_name} 不存在"}
    
    from_info = wallets[from_name]
    from_addr = Web3.to_checksum_address(from_info['address'])
    key = from_info.get('private_key') or from_info.get('privateKey')
    if not key.startswith('0x'):
        key = '0x' + key
    
    to_cs = Web3.to_checksum_address(to_addr)
    nonce = w3.eth.get_transaction_count(from_addr)
    
    tx = {
        'from': from_addr,
        'to': to_cs,
        'value': w3.to_wei(amount, 'ether'),
        'gas': 25000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
    }
    
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    if receipt.status == 1:
        return {"ok": True, "txHash": tx_hash.hex()}
    else:
        return {"ok": False, "error": "交易失败"}

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python3 transfer_bnb.py <from_name> <to_addr> <amount>")
        sys.exit(1)
    
    from_name = sys.argv[1]
    to_addr = sys.argv[2]
    amount = float(sys.argv[3])
    
    result = transfer_bnb(from_name, to_addr, amount)
    print(json.dumps(result))
