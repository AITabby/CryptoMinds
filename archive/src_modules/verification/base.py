"""
验证门抽象基类

每个验证门定义一类任务的验证逻辑：
- 输入格式验证
- 输出格式验证
- 任务完成判定
- 质量评分
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import time


@dataclass
class VerificationResult:
    """验证结果"""
    success: bool                    # 任务是否完成
    score: float = 0.0               # 质量分 0-1
    gate_id: str = ""                # 验证门 ID
    task_type: str = ""              # 任务类型
    chain: str = ""                  # 链（如果适用）
    evidence: Dict = field(default_factory=dict)  # 验证证据
    error: str = ""                  # 错误信息
    verified_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "score": self.score,
            "gate_id": self.gate_id,
            "task_type": self.task_type,
            "chain": self.chain,
            "evidence": self.evidence,
            "error": self.error,
            "verified_at": self.verified_at,
        }


@dataclass
class TaskInput:
    """任务输入"""
    task_type: str                   # 任务类型
    buyer_wallet: str                # 买家钱包
    seller_wallet: str = ""          # 卖家钱包
    chain: str = ""                  # 链（如果适用）
    token_address: str = ""          # 代币地址（如果适用）
    amount: Decimal = Decimal("0")   # 金额
    params: Dict = field(default_factory=dict)  # 其他参数

    def to_dict(self) -> Dict:
        return {
            "task_type": self.task_type,
            "buyer_wallet": self.buyer_wallet,
            "seller_wallet": self.seller_wallet,
            "chain": self.chain,
            "token_address": self.token_address,
            "amount": str(self.amount),
            "params": self.params,
        }


@dataclass
class TaskOutput:
    """任务输出（卖家提交）"""
    task_type: str                   # 任务类型
    seller_wallet: str = ""          # 卖家钱包
    tx_hash: str = ""                # 交易哈希（如果适用）
    token_address: str = ""          # 代币地址（如果适用）
    token_amount: str = ""           # 代币数量（如果适用）
    data: str = ""                   # 数据（如果适用）
    file_hash: str = ""              # 文件哈希（如果适用）
    extra: Dict = field(default_factory=dict)  # 其他输出

    def to_dict(self) -> Dict:
        return {
            "task_type": self.task_type,
            "seller_wallet": self.seller_wallet,
            "tx_hash": self.tx_hash,
            "token_address": self.token_address,
            "token_amount": self.token_amount,
            "data": self.data,
            "file_hash": self.file_hash,
            "extra": self.extra,
        }


class VerificationGate(ABC):
    """
    验证门抽象基类

    每个验证门负责验证一类任务：
    - token_delivery: 代币交付
    - data_delivery: 数据交付
    - compute_result: 计算结果
    - content_delivery: 内容交付
    """

    gate_id: str = ""
    task_type: str = ""
    version: str = "1.0.0"
    description: str = ""
    supported_chains: List[str] = []

    # ── 输入/输出验证 ─────────────────────────────────

    @abstractmethod
    def validate_input(self, input: TaskInput) -> Tuple[bool, str]:
        """
        验证输入格式

        Returns:
            (valid, message)
        """
        pass

    @abstractmethod
    def validate_output(self, output: TaskOutput) -> Tuple[bool, str]:
        """
        验证输出格式

        Returns:
            (valid, message)
        """
        pass

    # ── 核心验证逻辑 ───────────────────────────────────

    @abstractmethod
    def verify(self, input: TaskInput, output: TaskOutput) -> VerificationResult:
        """
        验证任务是否完成

        这是核心方法，由子类实现具体验证逻辑。

        Args:
            input: 任务输入
            output: 卖家提交的输出

        Returns:
            VerificationResult
        """
        pass

    # ── 辅助方法 ───────────────────────────────────────

    def supports_chain(self, chain: str) -> bool:
        """检查是否支持指定链"""
        if not self.supported_chains:
            return True  # 未指定则支持所有链
        return chain.lower() in [c.lower() for c in self.supported_chains]

    def to_dict(self) -> Dict:
        """返回验证门信息"""
        return {
            "gate_id": self.gate_id,
            "task_type": self.task_type,
            "version": self.version,
            "description": self.description,
            "supported_chains": self.supported_chains,
        }
