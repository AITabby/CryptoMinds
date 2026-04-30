"""
BSC 原生通道 - BNB 转账

基于现有 x402_pay.py 重构，支持：
- 直接 BNB 转账
- 合约托管（基于 ServiceEscrow.sol）
"""

import os
import json
import hashlib
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple
from pathlib import Path

from ..base import SettlementChannel, PaymentRequest, PaymentResult, EscrowResult

# 配置
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org")
BSC_CHAIN_ID = 56
TEST_MODE = os.getenv("SETTLEMENT_TEST_MODE", "false").lower() == "true"


class BSCNativeChannel(SettlementChannel):
    """
    BSC 链 BNB 原生转账通道

    channel_id: bsc-native
    chain: bsc
    token: bnb
    """

    channel_id = "bsc-native"
    chain = "bsc"
    token = "bnb"
    decimals = 18
    supports_escrow = True

    def __init__(self, rpc_url: str = None, test_mode: bool = None):
        self.rpc_url = rpc_url or BSC_RPC
        self.test_mode = test_mode if test_mode is not None else TEST_MODE
        self._w3 = None

    @property
    def w3(self):
        """懒加载 Web3 实例"""
        if self._w3 is None:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return self._w3

    # ── 查询 ─────────────────────────────────────────

    def get_balance(self, address: str) -> Decimal:
        """查询 BNB 余额"""
        try:
            from web3 import Web3
            balance = self.w3.eth.get_balance(Web3.to_checksum_address(address))
            return Decimal(str(self.w3.from_wei(balance, 'ether')))
        except Exception as e:
            print(f"查询 BNB 余额失败: {e}")
            return Decimal("0")

    def is_address_valid(self, address: str) -> bool:
        """验证 BSC 地址格式"""
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
        """创建 BNB 支付请求"""
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
            # 降级：HMAC 签名
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
        """执行 BNB 转账"""

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

            tx = {
                'chainId': BSC_CHAIN_ID,
                'to': Web3.to_checksum_address(request.to_address),
                'value': amount_wei,
                'gas': 21000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': nonce,
            }

            # 签名并发送
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction')
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            tx_hash_hex = tx_hash.hex()

            # 等待确认
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

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
                return False, f"金额不匹配: 期望 {expected_wei}, 实际 {tx['value']}"

            return True, "支付验证通过"

        except Exception as e:
            return False, f"验证失败: {e}"

    # ── 托管支付 ─────────────────────────────────────

    def escrow_lock(
        self,
        buyer_address: str,
        seller_address: str,
        amount: Decimal,
        order_id: str,
        timeout_seconds: int = 1800,
        **kwargs
    ) -> EscrowResult:
        """
        通过 ServiceEscrow 合约锁定资金

        注意：这需要前端通过 MetaMask 调用合约
        这里返回合约调用参数，供前端使用
        """
        # TODO: 实现合约托管逻辑
        # 当前返回合约调用信息，供前端使用
        return EscrowResult(
            success=False,
            error="合约托管需要前端通过 MetaMask 调用，请使用 escrow_prepare_contract_call",
        )

    def escrow_prepare_contract_call(
        self,
        seller_address: str,
        order_id: str,
        buyer_timeout_seconds: int = 86400,
        seller_timeout_seconds: int = 1800,
    ) -> Dict:
        """
        准备合约调用参数

        返回前端 MetaMask 需要的参数
        """
        return {
            "contract_address": os.getenv("BSCEscrow_CONTRACT", ""),
            "method": "createOrder",
            "args": [
                seller_address,
                order_id,
                buyer_timeout_seconds,
                seller_timeout_seconds,
            ],
            "abi": self._get_escrow_abi(),
        }

    def _get_escrow_abi(self) -> list:
        """获取 ServiceEscrow 合约 ABI"""
        abi_path = Path(__file__).parent.parent.parent / "contracts" / "ServiceEscrow_sol_ServiceEscrow.abi"
        if abi_path.exists():
            return json.loads(abi_path.read_text())
        return []
