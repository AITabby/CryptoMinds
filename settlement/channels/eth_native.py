"""
ETH 原生通道 - ETH 转账

支持 Ethereum 主网的原生 ETH 转账。
"""

import os
import hashlib
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple

from ..base import SettlementChannel, PaymentRequest, PaymentResult, EscrowResult

# 配置
ETH_RPC = os.getenv("ETH_RPC", "https://eth.llamarpc.com")
ETH_CHAIN_ID = 1
TEST_MODE = os.getenv("SETTLEMENT_TEST_MODE", "false").lower() == "true"


class ETHNativeChannel(SettlementChannel):
    """
    ETH 链 ETH 原生转账通道

    channel_id: eth-native
    chain: eth
    token: eth
    """

    channel_id = "eth-native"
    chain = "eth"
    token = "eth"
    decimals = 18
    supports_escrow = True  # 可以部署托管合约

    def __init__(self, rpc_url: str = None, test_mode: bool = None):
        self.rpc_url = rpc_url or ETH_RPC
        self.test_mode = test_mode if test_mode is not None else TEST_MODE
        self._w3 = None

    @property
    def w3(self):
        """懒加载 Web3 实例"""
        if self._w3 is None:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        return self._w3

    # ── 查询 ─────────────────────────────────────────

    def get_balance(self, address: str) -> Decimal:
        """查询 ETH 余额"""
        try:
            from web3 import Web3
            balance = self.w3.eth.get_balance(Web3.to_checksum_address(address))
            return Decimal(str(self.w3.from_wei(balance, 'ether')))
        except Exception as e:
            print(f"查询 ETH 余额失败: {e}")
            return Decimal("0")

    def is_address_valid(self, address: str) -> bool:
        """验证 ETH 地址格式"""
        try:
            from web3 import Web3
            return Web3.is_address(address)
        except:
            return False

    # ── 直接支付 ─────────────────────────────────────

    def create_payment(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        order_id: str,
        description: str = "",
        **kwargs
    ) -> PaymentRequest:
        """创建 ETH 支付请求"""
        return PaymentRequest(
            channel_id=self.channel_id,
            chain=self.chain,
            token=self.token,
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            order_id=order_id,
            description=description,
            extra=kwargs,
        )

    def sign_payment(self, request: PaymentRequest, private_key: str) -> str:
        """签名支付请求"""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            if not private_key.startswith("0x"):
                private_key = "0x" + private_key

            message = request.to_sign_message()
            encoded = encode_defunct(text=message)
            signed = Account.sign_message(encoded, private_key=private_key)
            return signed.signature.hex()
        except ImportError:
            import hmac
            message = request.to_sign_message()
            return hmac.new(
                private_key.encode() if isinstance(private_key, str) else private_key,
                message.encode(),
                hashlib.sha256
            ).hexdigest()

    def execute_payment(
        self,
        request: PaymentRequest,
        signature: str,
        private_key: str
    ) -> PaymentResult:
        """执行 ETH 转账"""

        # 测试模式：模拟交易
        if self.test_mode:
            return self._execute_mock(request, signature)

        # 真实链上交易
        try:
            from web3 import Web3

            if not private_key.startswith("0x"):
                private_key = "0x" + private_key

            # 构造交易
            amount_wei = self.w3.to_wei(float(request.amount), 'ether')
            nonce = self.w3.eth.get_transaction_count(request.from_address)

            # EIP-1559 交易
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            max_priority_fee = self.w3.eth.max_priority_fee
            max_fee = base_fee + max_priority_fee

            tx = {
                'type': 0x2,  # EIP-1559
                'chainId': ETH_CHAIN_ID,
                'to': Web3.to_checksum_address(request.to_address),
                'value': amount_wei,
                'gas': 21000,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': max_priority_fee,
                'nonce': nonce,
            }

            # 签名并发送
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            # 等待确认（ETH 区块时间约 12 秒）
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                return PaymentResult(
                    success=True,
                    tx_hash=tx_hash_hex,
                    channel_id=self.channel_id,
                    chain=self.chain,
                    token=self.token,
                    from_address=request.from_address,
                    to_address=request.to_address,
                    amount=request.amount,
                    order_id=request.order_id,
                    nonce=request.nonce,
                    signature=signature,
                    block_number=receipt.blockNumber,
                    proof={"gas_used": receipt.gasUsed},
                )
            else:
                return PaymentResult(
                    success=False,
                    error="交易执行失败",
                    channel_id=self.channel_id,
                    order_id=request.order_id,
                )

        except Exception as e:
            return PaymentResult(
                success=False,
                error=f"链上交易失败: {e}",
                channel_id=self.channel_id,
                order_id=request.order_id,
            )

    def _execute_mock(self, request: PaymentRequest, signature: str) -> PaymentResult:
        """测试模式：模拟交易"""
        fake_tx_hash = "0x" + hashlib.sha256(
            f"{time.time()}{request.from_address}{request.to_address}".encode()
        ).hexdigest()[:64]

        return PaymentResult(
            success=True,
            tx_hash=fake_tx_hash,
            channel_id=self.channel_id,
            chain=self.chain,
            token=self.token,
            from_address=request.from_address,
            to_address=request.to_address,
            amount=request.amount,
            order_id=request.order_id,
            nonce=request.nonce,
            signature=signature,
            block_number=0,
            proof={"test_mode": True},
        )

    def verify_payment(self, result: PaymentResult) -> Tuple[bool, str]:
        """验证支付结果"""

        # 测试模式
        if result.proof.get("test_mode"):
            return True, "支付验证通过（测试模式）"

        try:
            from web3 import Web3

            tx_hash = result.tx_hash
            if not tx_hash:
                return False, "缺少交易哈希"

            # 获取交易回执
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt.status != 1:
                return False, "交易执行失败"

            # 获取交易详情
            tx = self.w3.eth.get_transaction(tx_hash)

            # 验证发送方
            if tx["from"].lower() != result.from_address.lower():
                return False, "交易发送方不匹配"

            # 验证接收方
            if tx["to"].lower() != result.to_address.lower():
                return False, "交易接收方不匹配"

            # 验证金额
            expected_wei = self.w3.to_wei(float(result.amount), 'ether')
            if tx["value"] != expected_wei:
                return False, f"金额不匹配"

            return True, "支付验证通过"

        except Exception as e:
            return False, f"验证失败: {e}"
