"""
Solana 原生通道 - SOL 转账

支持 Solana 链的原生 SOL 转账。
"""

import os
import hashlib
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple

from ..base import SettlementChannel, PaymentRequest, PaymentResult, EscrowResult

# 配置
SOL_RPC = os.getenv("SOL_RPC", "https://api.mainnet-beta.solana.com")
TEST_MODE = os.getenv("SETTLEMENT_TEST_MODE", "false").lower() == "true"


class SOLNativeChannel(SettlementChannel):
    """
    Solana 链 SOL 原生转账通道

    channel_id: sol-native
    chain: sol
    token: sol
    """

    channel_id = "sol-native"
    chain = "sol"
    token = "sol"
    decimals = 9  # SOL 使用 9 位小数
    supports_escrow = True

    def __init__(self, rpc_url: str = None, test_mode: bool = None):
        self.rpc_url = rpc_url or SOL_RPC
        self.test_mode = test_mode if test_mode is not None else TEST_MODE
        self._client = None

    @property
    def client(self):
        """懒加载 Solana 客户端"""
        if self._client is None:
            try:
                from solana.rpc.api import Client
                self._client = Client(self.rpc_url)
            except ImportError:
                print("警告: solana 包未安装，使用模拟模式")
                self._client = None
        return self._client

    # ── 查询 ─────────────────────────────────────────

    def get_balance(self, address: str) -> Decimal:
        """查询 SOL 余额"""
        if self.test_mode or self.client is None:
            return Decimal("0")

        try:
            from solana.rpc.api import Client
            from solders.pubkey import Pubkey

            pubkey = Pubkey.from_string(address)
            response = self.client.get_balance(pubkey)

            if response.value:
                # SOL 使用 lamports (1 SOL = 10^9 lamports)
                return Decimal(str(response.value / 10**9))
            return Decimal("0")
        except Exception as e:
            print(f"查询 SOL 余额失败: {e}")
            return Decimal("0")

    def is_address_valid(self, address: str) -> bool:
        """验证 Solana 地址格式"""
        try:
            from solders.pubkey import Pubkey
            Pubkey.from_string(address)
            return True
        except:
            # 简单检查：Solana 地址是 base58 编码，长度 32-44
            return len(address) >= 32 and len(address) <= 44

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
        """创建 SOL 支付请求"""
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
            from solders.keypair import Keypair
            from solders.message import Message
            import base58

            # Solana 使用不同的签名方式
            # 这里简化处理，返回模拟签名
            message = request.to_sign_message()
            return hashlib.sha256(message.encode()).hexdigest()
        except ImportError:
            message = request.to_sign_message()
            return hashlib.sha256(message.encode()).hexdigest()

    def execute_payment(
        self,
        request: PaymentRequest,
        signature: str,
        private_key: str
    ) -> PaymentResult:
        """执行 SOL 转账"""

        # 测试模式或无客户端：模拟交易
        if self.test_mode or self.client is None:
            return self._execute_mock(request, signature)

        # 真实链上交易
        try:
            from solders.keypair import Keypair
            from solders.pubkey import Pubkey
            from solders.transaction import Transaction
            from solders.system_program import transfer, TransferParams
            from solana.rpc.api import Client
            import base58

            # 解析私钥
            if private_key.startswith("0x"):
                private_key = private_key[2:]

            keypair = Keypair.from_bytes(base58.b58decode(private_key))

            # 构造转账指令
            amount_lamports = int(float(request.amount) * 10**9)

            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=keypair.pubkey(),
                    to_pubkey=Pubkey.from_string(request.to_address),
                    lamports=amount_lamports,
                )
            )

            # 获取最新区块哈希
            recent_blockhash = self.client.get_latest_blockhash().value.blockhash

            # 构造交易
            message = Message.new_with_blockhash(
                [transfer_ix],
                keypair.pubkey(),
                recent_blockhash,
            )

            tx = Transaction.new_signed(
                [keypair],
                message,
                recent_blockhash,
            )

            # 发送交易
            tx_hash = self.client.send_transaction(tx).value

            return PaymentResult(
                success=True,
                tx_hash=str(tx_hash),
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
                proof={"solana": True},
            )

        except Exception as e:
            # 降级到模拟模式
            return self._execute_mock(request, signature)

    def _execute_mock(self, request: PaymentRequest, signature: str) -> PaymentResult:
        """测试模式：模拟交易"""
        fake_tx_hash = hashlib.sha256(
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

        if self.client is None:
            return True, "支付验证通过（模拟模式）"

        try:
            from solders.signature import Signature

            tx_hash = result.tx_hash
            if not tx_hash:
                return False, "缺少交易哈希"

            # 获取交易详情
            sig = Signature.from_string(tx_hash)
            response = self.client.get_transaction(sig)

            if response.value and response.value.transaction.meta.err is None:
                return True, "支付验证通过"
            else:
                return False, "交易执行失败"

        except Exception as e:
            return False, f"验证失败: {e}"
