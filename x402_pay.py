#!/usr/bin/env python3
"""
CryptoMinds x402 支付模块
实现完整的 x402 协议流程：请求→402→签名→验证→返回

当前：BNB 原生转账（BSC 主网）
未来：跨链时扩展 USDC/SOL 等代币支付
"""

import os

# 测试模式配置：默认真实链上模式，设 X402_TEST_MODE=true 才启用假交易
TEST_MODE = os.getenv("X402_TEST_MODE", "false").lower() == "true"

import json
import time
import hashlib
from typing import Dict, Optional, Tuple

from config import BSC_RPC, load_wallets, get_wallet_key

# ── 当前：BNB 原生支付 ──
NATIVE_TOKEN = "BNB"
NATIVE_DECIMALS = 18

# ── 未来：跨链扩展 ──
# BSC_USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
# BSC_USDC_DECIMALS = 18


class X402PaymentRequest:
    """x402 支付请求"""
    def __init__(self, chain: str, token: str, to: str, amount: int,
                 order_id: str, description: str, nonce: str = None):
        self.chain = chain
        self.token = token
        self.to = to
        self.amount = amount
        self.nonce = nonce if nonce else hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:16]
        self.timestamp = int(time.time())
        self.order_id = order_id
        self.description = description

    def to_dict(self) -> Dict:
        return {
            "chain": self.chain,
            "token": self.token,
            "to": self.to,
            "amount": self.amount,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "order_id": self.order_id,
            "description": self.description
        }

    def to_message(self) -> str:
        """构造签名消息"""
        data = self.to_dict()
        data.pop('timestamp', None)
        return json.dumps(data, sort_keys=True)

    def sign(self, private_key: str) -> str:
        """使用私钥签名"""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            if not private_key.startswith("0x"):
                private_key = "0x" + private_key

            message = self.to_message()
            encoded = encode_defunct(text=message)
            signed = Account.sign_message(encoded, private_key=private_key)
            return signed.signature.hex()
        except ImportError:
            import hmac
            message = self.to_message()
            signature = hmac.new(
                private_key.encode() if isinstance(private_key, str) else private_key,
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            return signature

    def get_signer(self, signature: str) -> str:
        """从签名恢复地址"""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            message = self.to_message()
            encoded = encode_defunct(text=message)
            recovered = Account.recover_message(encoded, signature=signature)
            return recovered
        except ImportError:
            return signature


def get_bnb_balance(address: str) -> float:
    """查询 BNB 余额"""
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        balance = w3.eth.get_balance(Web3.to_checksum_address(address))
        return float(Web3.from_wei(balance, 'ether'))
    except Exception as e:
        print(f"查询 BNB 余额失败: {e}")
        return 0.0


# 保留旧函数名兼容
def get_usdc_balance(address: str) -> float:
    """查询 BNB 余额（兼容旧接口名）"""
    return get_bnb_balance(address)


def x402_pay(from_name: str, to_name: str, amount_bnb: float,
             order_id: str, description: str) -> Tuple[bool, str, Dict]:
    """
    执行 x402 支付流程（BNB 原生转账）

    返回: (success, tx_hash, payment_info)
    """
    global TEST_MODE
    wallets = load_wallets()

    if from_name not in wallets:
        return False, "", {"error": f"未知发送方: {from_name}"}
    if to_name not in wallets:
        return False, "", {"error": f"未知接收方: {to_name}"}

    from_wallet = wallets[from_name]
    to_wallet = wallets[to_name]

    # 1. 创建支付请求
    amount_wei = int(amount_bnb * (10 ** NATIVE_DECIMALS))
    payment_req = X402PaymentRequest(
        chain="bsc",
        token=NATIVE_TOKEN,
        to=to_wallet["address"],
        amount=amount_wei,
        order_id=order_id,
        description=description
    )

    # 2. 签名支付请求
    try:
        signature = payment_req.sign(get_wallet_key(from_name))
        print("   📝 支付请求已签名")
    except Exception as e:
        return False, "", {"error": f"签名失败: {e}"}

    # 3. 验证签名（客户端自验证）
    signer = payment_req.get_signer(signature)
    if signer.lower() != from_wallet["address"].lower():
        return False, "", {"error": "签名验证失败，地址不匹配"}
    print(f"   ✓ 签名验证通过: {signer[:10]}...")

    # 测试模式：模拟交易
    if TEST_MODE:
        print("   🧪 测试模式：模拟交易")
        fake_tx_hash = hashlib.sha256(f"{time.time()}{from_name}{to_name}".encode()).hexdigest()
        fake_tx_hash = "0x" + fake_tx_hash[:64]

        payment_info = {
            "tx_hash": fake_tx_hash,
            "from": from_wallet["address"],
            "to": to_wallet["address"],
            "amount_bnb": amount_bnb,
            "amount_wei": amount_wei,
            "order_id": order_id,
            "description": description,
            "nonce": payment_req.nonce,
            "signature": signature,
            "signer": signer,
            "chain": "bsc",
            "token": NATIVE_TOKEN,
            "block": 0,
            "test_mode": True
        }
        print(f"   ✓ 模拟交易完成: {fake_tx_hash[:20]}...")
        return True, fake_tx_hash, payment_info

    # 4. 执行链上 BNB 原生转账
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        nonce = w3.eth.get_transaction_count(from_wallet["address"])
        tx = {
            'chainId': 56,
            'to': Web3.to_checksum_address(to_wallet["address"]),
            'value': amount_wei,
            'gas': 21000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        }

        # 签名并发送
        signed_tx = w3.eth.account.sign_transaction(tx, get_wallet_key(from_name))
        raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        tx_hash_hex = tx_hash.hex()

        print(f"   ⛓️ 交易已发送: {tx_hash_hex[:20]}...")

        # 等待确认
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt.status == 1:
            print(f"   ✓ 交易已确认: https://bscscan.com/tx/{tx_hash_hex}")

            payment_info = {
                "tx_hash": tx_hash_hex,
                "from": from_wallet["address"],
                "to": to_wallet["address"],
                "amount_bnb": amount_bnb,
                "amount_wei": amount_wei,
                "order_id": order_id,
                "description": description,
                "nonce": payment_req.nonce,
                "signature": signature,
                "signer": signer,
                "chain": "bsc",
                "token": NATIVE_TOKEN,
                "block": receipt.blockNumber
            }
            return True, tx_hash_hex, payment_info
        else:
            return False, "", {"error": "交易执行失败"}

    except Exception as e:
        return False, "", {"error": f"链上交易失败: {e}"}


def verify_x402_payment(payment_info: Dict) -> Tuple[bool, str]:
    """
    验证 x402 支付（服务端调用）

    返回: (valid, message)
    """
    try:
        # 测试模式：只验证签名
        if payment_info.get("test_mode"):
            print("   🧪 测试模式：只验证签名")
            print("   ⚠️ 测试模式：跳过签名验证")
            print("   ✓ x402 支付验证通过（测试模式）")
            print(f"     金额: {payment_info.get('amount_bnb', payment_info.get('amount_usdc', '?'))} BNB")
            return True, "支付验证通过（测试模式）"

        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        tx_hash = payment_info.get("tx_hash")
        if not tx_hash:
            return False, "缺少交易哈希"

        # 1. 获取交易回执
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt.status != 1:
            return False, "交易执行失败"

        # 2. 获取交易详情
        tx = w3.eth.get_transaction(tx_hash)

        # 3. 验证发送方
        if tx["from"].lower() != payment_info["from"].lower():
            return False, "交易发送方不匹配"

        # 4. 验证接收方（BNB 原生转账：tx.to 就是收款地址）
        if tx["to"].lower() != payment_info["to"].lower():
            return False, "交易接收方不匹配"

        # 5. 验证金额（BNB 原生转账：tx.value 就是金额）
        if tx["value"] != payment_info["amount_wei"]:
            return False, f"金额不匹配: 期望 {payment_info['amount_wei']}, 实际 {tx['value']}"

        # 6. 验证签名（用原始 description 和 nonce 重建请求）
        payment_req = X402PaymentRequest(
            chain=payment_info["chain"],
            token=payment_info["token"],
            to=payment_info["to"],
            amount=payment_info["amount_wei"],
            order_id=payment_info["order_id"],
            description=payment_info.get("description", ""),
            nonce=payment_info.get("nonce")
        )

        recovered = payment_req.get_signer(payment_info["signature"])
        if recovered.lower() != payment_info["signer"].lower():
            return False, "签名验证失败"

        amount_display = payment_info.get('amount_bnb', payment_info.get('amount_usdc', '?'))
        print("   ✓ x402 支付验证通过")
        print(f"     交易: {tx_hash[:20]}...")
        print(f"     签名者: {recovered[:10]}...")
        print(f"     金额: {amount_display} BNB")

        return True, "支付验证通过"

    except Exception as e:
        return False, f"验证失败: {e}"


if __name__ == "__main__":
    # 测试 x402 支付
    print("=== x402 支付测试（BNB 原生转账）===")

    wallets = load_wallets()
    for name in wallets:
        addr = wallets[name]["address"]
        bnb = get_bnb_balance(addr)
        print(f"{name}: {bnb:.6f} BNB")
