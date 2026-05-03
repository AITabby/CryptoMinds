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
            raise RuntimeError("eth_account is required for signing — HMAC fallback removed for security")

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
        """买家通过 MetaMask 调用 createOrder, 不在此处直接链上锁定"""
        return EscrowResult(
            success=False,
            error="合约托管需要前端通过 MetaMask 调用，请使用 escrow_prepare_contract_call",
        )

    def _get_contract_address(self, version: str = "v1") -> str:
        """获取合约部署地址。version='v1' 或 'v2'"""
        if version == "v2":
            env_addr = os.getenv("ESCROW_V2_CONTRACT_ADDRESS", "")
            if env_addr:
                return env_addr
            deploy_path = Path(__file__).parent.parent.parent / "escrow_deployment_v2.json"
            if deploy_path.exists():
                deploy_data = json.loads(deploy_path.read_text())
                return deploy_data.get("contractAddress", "")
            return ""
        # V1 (default)
        env_addr = os.getenv("ESCROW_CONTRACT_ADDRESS", "")
        if env_addr:
            return env_addr
        deploy_path = Path(__file__).parent.parent.parent / "escrow_deployment.json"
        if deploy_path.exists():
            deploy_data = json.loads(deploy_path.read_text())
            return deploy_data.get("address", "")
        return ""

    def escrow_prepare_contract_call(
        self,
        action: str,
        **kwargs,
    ) -> Dict:
        """
        准备合约调用参数，供前端 MetaMask 使用

        action: createOrder, deliver, confirm, dispute, claimBuyerTimeout, claimSellerTimeout
        """
        from web3 import Web3

        contract_address = self._get_contract_address()
        abi = self._get_escrow_abi()

        if action == "createOrder":
            token = kwargs.get("token", "bnb").lower()
            version = "v2" if token != "bnb" else "v1"
            contract_address = self._get_contract_address(version)
            abi = self._get_escrow_abi(version)
            if token == "bnb":
                return {
                    "contract_address": contract_address,
                    "method": "createOrder",
                    "args": [
                        kwargs.get("seller_address", ""),
                        kwargs.get("order_id", ""),
                        kwargs.get("buyer_timeout_seconds", 86400),
                        kwargs.get("seller_timeout_seconds", 1800),
                    ],
                    "value": str(self.w3.to_wei(float(kwargs.get("amount", 0)), 'ether')),
                    "abi": abi,
                }
            else:
                # ERC-20 mode: no BNB value, amount as parameter
                amount_wei = self.w3.to_wei(float(kwargs.get("amount", 0)), 'ether')
                return {
                    "contract_address": contract_address,
                    "method": "createOrder",
                    "args": [
                        kwargs.get("seller_address", ""),
                        kwargs.get("order_id", ""),
                        kwargs.get("buyer_timeout_seconds", 86400),
                        kwargs.get("seller_timeout_seconds", 1800),
                        str(amount_wei),
                    ],
                    "value": "0",
                    "token": token,
                    "token_address": kwargs.get("token_address", ""),
                    "approve_required": True,
                    "approve_amount": str(amount_wei),
                    "abi": abi,
                }
        elif action == "deliver":
            return {
                "contract_address": contract_address,
                "method": "deliver",
                "args": [
                    kwargs.get("on_chain_order_id", ""),
                    kwargs.get("result", ""),
                ],
                "abi": abi,
            }
        elif action == "confirm":
            return {
                "contract_address": contract_address,
                "method": "confirm",
                "args": [kwargs.get("on_chain_order_id", "")],
                "abi": abi,
            }
        elif action == "dispute":
            return {
                "contract_address": contract_address,
                "method": "dispute",
                "args": [kwargs.get("on_chain_order_id", "")],
                "abi": abi,
            }
        elif action in ("claimBuyerTimeout", "claimSellerTimeout"):
            return {
                "contract_address": contract_address,
                "method": action,
                "args": [kwargs.get("on_chain_order_id", "")],
                "abi": abi,
            }
        else:
            return {"error": f"unsupported action: {action}"}

    def escrow_confirm_on_chain(
        self,
        escrow_id: str,
        on_chain_order_id: str,
        admin_private_key: str,
    ) -> EscrowResult:
        """管理员调用 arbitrateRelease (owner-only)"""
        from web3 import Web3

        if not admin_private_key.startswith("0x"):
            admin_private_key = "0x" + admin_private_key

        contract_address = self._get_contract_address()
        if not contract_address:
            return EscrowResult(success=False, error="合约地址未配置")

        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=self._get_escrow_abi(),
            )

            admin_account = self.w3.eth.account.from_key(admin_private_key)
            nonce = self.w3.eth.get_transaction_count(admin_account.address)

            order_id_bytes = Web3.to_bytes(hexstr=on_chain_order_id) if on_chain_order_id.startswith("0x") else Web3.to_bytes(text=on_chain_order_id)

            tx = contract.functions.arbitrateRelease(order_id_bytes).build_transaction({
                'from': admin_account.address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': BSC_CHAIN_ID,
            })

            signed = self.w3.eth.account.sign_transaction(tx, admin_private_key)
            raw_tx = getattr(signed, 'raw_transaction', None) or getattr(signed, 'rawTransaction')
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                return EscrowResult(success=True, escrow_id=escrow_id, tx_hash=tx_hash.hex())
            return EscrowResult(success=False, error="on-chain arbitrateRelease failed")
        except Exception as e:
            return EscrowResult(success=False, error=str(e))

    def escrow_refund_on_chain(
        self,
        escrow_id: str,
        on_chain_order_id: str,
        reason: str,
        admin_private_key: str,
    ) -> EscrowResult:
        """管理员调用 arbitrateRefund (owner-only)"""
        from web3 import Web3

        if not admin_private_key.startswith("0x"):
            admin_private_key = "0x" + admin_private_key

        contract_address = self._get_contract_address()
        if not contract_address:
            return EscrowResult(success=False, error="合约地址未配置")

        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=self._get_escrow_abi(),
            )

            admin_account = self.w3.eth.account.from_key(admin_private_key)
            nonce = self.w3.eth.get_transaction_count(admin_account.address)

            order_id_bytes = Web3.to_bytes(hexstr=on_chain_order_id) if on_chain_order_id.startswith("0x") else Web3.to_bytes(text=on_chain_order_id)

            tx = contract.functions.arbitrateRefund(order_id_bytes, reason).build_transaction({
                'from': admin_account.address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': BSC_CHAIN_ID,
            })

            signed = self.w3.eth.account.sign_transaction(tx, admin_private_key)
            raw_tx = getattr(signed, 'raw_transaction', None) or getattr(signed, 'rawTransaction')
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                return EscrowResult(success=True, escrow_id=escrow_id, tx_hash=tx_hash.hex())
            return EscrowResult(success=False, error="on-chain arbitrateRefund failed")
        except Exception as e:
            return EscrowResult(success=False, error=str(e))

    def escrow_sync_state(
        self,
        on_chain_order_id: str,
    ) -> Dict:
        """读取链上订单状态, 映射为 EscrowState"""
        from web3 import Web3
        from settlement.escrow_state import EscrowState

        contract_address = self._get_contract_address()
        if not contract_address:
            return {"error": "合约地址未配置"}

        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=self._get_escrow_abi(),
            )

            order_id_bytes = Web3.to_bytes(hexstr=on_chain_order_id) if on_chain_order_id.startswith("0x") else Web3.to_bytes(text=on_chain_order_id)

            order_data = contract.functions.getOrder(order_id_bytes).call()

            chain_status = order_data[8]
            return {
                "buyer": order_data[0],
                "seller": order_data[1],
                "serviceId": order_data[2],
                "amount": str(self.w3.from_wei(order_data[3], 'ether')),
                "createdAt": order_data[4],
                "deliveredAt": order_data[5],
                "buyerTimeoutAt": order_data[6],
                "sellerTimeoutAt": order_data[7],
                "status": chain_status,
                "status_mapped": EscrowState.from_chain_status(chain_status).value,
                "deliverResult": order_data[9],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_escrow_abi(self, version: str = "v1") -> list:
        """获取合约 ABI。version='v1' 或 'v2'"""
        if version == "v2":
            abi_path = Path(__file__).parent.parent.parent / "build" / "contracts_ServiceEscrowV2_sol_ServiceEscrowV2.abi"
        else:
            abi_path = Path(__file__).parent.parent.parent / "build" / "contracts_ServiceEscrow_sol_ServiceEscrow.abi"
        if abi_path.exists():
            return json.loads(abi_path.read_text())
        return []

    def escrow_prepare_approve(self, token_address: str, amount_wei: int, spender: str = "") -> Dict:
        """准备 ERC-20 approve 调用参数，供前端 MetaMask 使用"""
        if not spender:
            spender = self._get_contract_address("v2")
        approve_abi = [{"inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"}]
        return {
            "contract_address": token_address,
            "method": "approve",
            "args": [spender, str(amount_wei)],
            "value": "0",
            "abi": approve_abi,
        }
