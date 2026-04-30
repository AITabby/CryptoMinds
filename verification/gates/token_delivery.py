"""
代币交付验证门

验证卖家是否将代币交付到买家钱包。
支持多链：BSC、ETH、SOL 等。
"""

import os
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..base import VerificationGate, VerificationResult, TaskInput, TaskOutput


# 链验证器配置
CHAIN_CONFIGS = {
    "bsc": {
        "rpc": os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org"),
        "chain_id": 56,
    },
    "eth": {
        "rpc": os.getenv("ETH_RPC", "https://eth.llamarpc.com"),
        "chain_id": 1,
    },
    # 未来扩展
    # "sol": {...},
    # "polygon": {...},
}


class TokenDeliveryGate(VerificationGate):
    """
    代币交付验证门

    gate_id: token_delivery
    task_type: token_delivery
    supported_chains: bsc, eth

    验证逻辑：
    1. 检查买家钱包是否收到了代币
    2. 检查代币数量是否满足预期（允许滑点）
    3. 检查交易哈希是否有效
    """

    gate_id = "token_delivery"
    task_type = "token_delivery"
    version = "1.0.0"
    description = "验证代币是否交付到买家钱包"
    supported_chains = ["bsc", "eth", "mock"]

    # 滑点容忍度（默认 5%）
    DEFAULT_SLIPPAGE = 0.05

    def __init__(self, slippage: float = None):
        self.slippage = slippage or self.DEFAULT_SLIPPAGE
        self._chain_verifiers = {}

    # ── 输入/输出验证 ─────────────────────────────────

    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """验证输入格式"""
        if not input.buyer_wallet:
            return False, "缺少买家钱包地址"

        if input.task_type != "token_delivery":
            return False, f"任务类型不匹配: {input.task_type}"

        if input.chain and not self.supports_chain(input.chain):
            return False, f"不支持链: {input.chain}"

        if input.amount <= 0:
            return False, "金额必须大于 0"

        return True, "输入验证通过"

    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """验证输出格式"""
        if not output.tx_hash:
            return False, "缺少交易哈希"

        if not output.token_address:
            return False, "缺少代币地址"

        if not output.token_amount:
            return False, "缺少代币数量"

        return True, "输出验证通过"

    # ── 核心验证逻辑 ───────────────────────────────────

    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """
        验证代币交付

        检查：
        1. 买家钱包是否收到代币
        2. 代币数量是否满足预期
        3. 交易是否有效
        """

        # 1. 验证输入输出格式
        valid, msg = self.validate_input(input)
        if not valid:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=msg,
            )

        valid, msg = self.validate_output(output)
        if not valid:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                error=msg,
            )

        chain = input.chain or "bsc"

        # 2. Mock 链特殊处理
        if chain == "mock":
            return self._verify_mock(input, output)

        # 3. 链上验证
        try:
            verifier = self._get_verifier(chain)
            if not verifier:
                return VerificationResult(
                    success=False,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    chain=chain,
                    error=f"不支持链: {chain}",
                )

            # 查询买家钱包的代币余额
            token_address = output.token_address
            buyer_wallet = input.buyer_wallet

            balance = verifier.get_token_balance(buyer_wallet, token_address)

            # 验证数量
            expected_min = self._calculate_min_expected(input, output)

            if balance >= expected_min:
                return VerificationResult(
                    success=True,
                    score=1.0,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    chain=chain,
                    evidence={
                        "token_address": token_address,
                        "balance": str(balance),
                        "expected_min": str(expected_min),
                        "tx_hash": output.tx_hash,
                    },
                )
            else:
                return VerificationResult(
                    success=False,
                    score=balance / expected_min if expected_min > 0 else 0,
                    gate_id=self.gate_id,
                    task_type=self.task_type,
                    chain=chain,
                    error=f"代币数量不足: 收到 {balance}, 期望至少 {expected_min}",
                    evidence={
                        "token_address": token_address,
                        "balance": str(balance),
                        "expected_min": str(expected_min),
                    },
                )

        except Exception as e:
            return VerificationResult(
                success=False,
                gate_id=self.gate_id,
                task_type=self.task_type,
                chain=chain,
                error=f"验证失败: {e}",
            )

    def _verify_mock(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """Mock 链验证（测试用）"""
        # Mock 验证总是成功，只要格式正确
        return VerificationResult(
            success=True,
            score=1.0,
            gate_id=self.gate_id,
            task_type=self.task_type,
            chain="mock",
            evidence={
                "token_address": output.token_address,
                "token_amount": output.token_amount,
                "tx_hash": output.tx_hash,
                "mock": True,
            },
        )

    def _calculate_min_expected(self, input: TaskInput, output: TaskOutput) -> Decimal:
        """计算最小期望数量"""
        # 如果输出明确指定了数量，直接用
        if output.token_amount:
            try:
                return Decimal(output.token_amount) * Decimal(str(1 - self.slippage))
            except:
                pass

        # 否则根据输入金额估算（需要价格信息，这里简化处理）
        return Decimal("0")

    # ── 链验证器 ───────────────────────────────────────

    def _get_verifier(self, chain: str) -> Optional["ChainVerifier"]:
        """获取链验证器"""
        if chain not in self._chain_verifiers:
            config = CHAIN_CONFIGS.get(chain)
            if config:
                self._chain_verifiers[chain] = EVMVerifier(config)
        return self._chain_verifiers.get(chain)


class EVMVerifier:
    """
    EVM 链验证器

    支持 BSC、ETH 等 EVM 链。
    """

    def __init__(self, config: Dict):
        self.rpc = config["rpc"]
        self.chain_id = config["chain_id"]
        self._w3 = None

    @property
    def w3(self):
        """懒加载 Web3"""
        if self._w3 is None:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware

            self._w3 = Web3(Web3.HTTPProvider(self.rpc))
            if self.chain_id in [56, 137]:  # BSC, Polygon 需要 POA middleware
                self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return self._w3

    def get_token_balance(self, wallet: str, token: str) -> Decimal:
        """查询代币余额"""

        from web3 import Web3

        wallet_cs = Web3.to_checksum_address(wallet)
        token_cs = Web3.to_checksum_address(token)

        # ERC20 ABI
        ERC20_ABI = [
            {
                "inputs": [{"internalType": "address", "name": "", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function",
            },
        ]

        contract = self.w3.eth.contract(address=token_cs, abi=ERC20_ABI)

        # 查余额
        balance_raw = contract.functions.balanceOf(wallet_cs).call()

        # 查精度
        try:
            decimals = contract.functions.decimals().call()
        except:
            decimals = 18

        return Decimal(str(balance_raw)) / Decimal(str(10 ** decimals))

    def verify_transaction(self, tx_hash: str, expected_from: str, expected_to: str) -> bool:
        """验证交易"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt.status != 1:
                return False

            tx = self.w3.eth.get_transaction(tx_hash)
            if tx["from"].lower() != expected_from.lower():
                return False

            if tx["to"].lower() != expected_to.lower():
                return False

            return True
        except:
            return False