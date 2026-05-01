"""
Agent 能力描述

定义 Agent 如何描述自己的能力，以及如何被其他 Agent 发现和匹配。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
import time


@dataclass
class CapabilitySpec:
    """
    能力规格

    描述 Agent 能执行的一类任务。
    """

    task_type: str                          # 任务类型（token_delivery, data_delivery, ...）
    verification_gate: str = ""             # 验证门 ID
    supported_chains: List[str] = field(default_factory=list)  # 支持的链
    supported_channels: List[str] = field(default_factory=list)  # 支持的结算通道

    # 任务参数
    params: Dict = field(default_factory=dict)  # 链特定参数
    # 例如:
    # {
    #     "bsc": {
    #         "max_amount_bnb": 1.0,
    #         "can_pick_token": true,
    #         "exchanges": ["four.meme", "pancakeswap"]
    #     },
    #     "sol": {
    #         "max_amount_sol": 10.0,
    #         "can_pick_token": true,
    #         "exchanges": ["raydium", "pump.fun"]
    #     }
    # }

    # 定价模型
    pricing_model: str = "fixed"            # fixed, percentage, dynamic
    base_price: Decimal = Decimal("0")      # 基础价格（固定定价）
    percentage_rate: Decimal = Decimal("0") # 百分比费率（百分比定价）

    # 可用性
    available: bool = True                  # 是否可用
    max_concurrent: int = 10                # 最大并发任务数

    def to_dict(self) -> Dict:
        return {
            "task_type": self.task_type,
            "verification_gate": self.verification_gate,
            "supported_chains": self.supported_chains,
            "supported_channels": self.supported_channels,
            "params": self.params,
            "pricing_model": self.pricing_model,
            "base_price": str(self.base_price),
            "percentage_rate": str(self.percentage_rate),
            "available": self.available,
            "max_concurrent": self.max_concurrent,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CapabilitySpec":
        """从字典创建"""
        return cls(
            task_type=data.get("task_type", ""),
            verification_gate=data.get("verification_gate", ""),
            supported_chains=data.get("supported_chains", []),
            supported_channels=data.get("supported_channels", []),
            params=data.get("params", {}),
            pricing_model=data.get("pricing_model", "fixed"),
            base_price=Decimal(str(data.get("base_price", 0))),
            percentage_rate=Decimal(str(data.get("percentage_rate", 0))),
            available=data.get("available", True),
            max_concurrent=data.get("max_concurrent", 10),
        )


@dataclass
class ReputationInfo:
    """
    信誉信息
    """

    score: float = 0.0                      # 综合评分 0-5
    tasks_completed: int = 0                # 完成任务数
    tasks_failed: int = 0                   # 失败任务数
    dispute_rate: float = 0.0               # 争议率 (争议任务/总任务)
    total_volume: Decimal = Decimal("0")    # 总交易量
    avg_response_time_ms: int = 0           # 平均响应时间（毫秒）

    # 最近表现
    last_24h_tasks: int = 0                 # 最近 24 小时任务数
    last_24h_success_rate: float = 1.0      # 最近 24 小时成功率

    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "dispute_rate": self.dispute_rate,
            "total_volume": str(self.total_volume),
            "avg_response_time_ms": self.avg_response_time_ms,
            "last_24h_tasks": self.last_24h_tasks,
            "last_24h_success_rate": self.last_24h_success_rate,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ReputationInfo":
        return cls(
            score=data.get("score", 0.0),
            tasks_completed=data.get("tasks_completed", 0),
            tasks_failed=data.get("tasks_failed", 0),
            dispute_rate=data.get("dispute_rate", 0.0),
            total_volume=Decimal(str(data.get("total_volume", 0))),
            avg_response_time_ms=data.get("avg_response_time_ms", 0),
            last_24h_tasks=data.get("last_24h_tasks", 0),
            last_24h_success_rate=data.get("last_24h_success_rate", 1.0),
        )

    @property
    def success_rate(self) -> float:
        """总成功率"""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 1.0
        return self.tasks_completed / total


@dataclass
class AgentCapability:
    """
    Agent 能力描述

    一个 Agent 可以有多种能力，每种能力对应一类任务。
    """

    agent_id: str                           # Agent 唯一标识
    name: str = ""                          # Agent 名称
    description: str = ""                   # Agent 描述
    wallet: str = ""                        # Agent 钱包地址
    endpoint: str = ""                      # Agent API 端点

    # 能力列表
    capabilities: List[CapabilitySpec] = field(default_factory=list)

    # 信誉
    reputation: ReputationInfo = field(default_factory=ReputationInfo)

    # 质押（用于接单额度）
    staked: Decimal = Decimal("0")          # 已质押金额
    active_tasks_value: Decimal = Decimal("0")  # 活跃任务价值

    # 元信息
    registered_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    online: bool = True

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "wallet": self.wallet,
            "endpoint": self.endpoint,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "reputation": self.reputation.to_dict(),
            "staked": str(self.staked),
            "active_tasks_value": str(self.active_tasks_value),
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "online": self.online,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentCapability":
        """从字典创建"""
        capabilities = [
            CapabilitySpec.from_dict(c) for c in data.get("capabilities", [])
        ]
        reputation = ReputationInfo.from_dict(data.get("reputation", {}))

        return cls(
            agent_id=data.get("agent_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            wallet=data.get("wallet", ""),
            endpoint=data.get("endpoint", ""),
            capabilities=capabilities,
            reputation=reputation,
            staked=Decimal(str(data.get("staked", 0))),
            active_tasks_value=Decimal(str(data.get("active_tasks_value", 0))),
            registered_at=data.get("registered_at", int(time.time())),
            updated_at=data.get("updated_at", int(time.time())),
            online=data.get("online", True),
        )

    # ── 便捷方法 ─────────────────────────────────────

    @property
    def available_quota(self) -> Decimal:
        """可用接单额度"""
        return max(Decimal("0"), self.staked - self.active_tasks_value)

    def can_accept(self, task_type: str, chain: str, amount: Decimal) -> bool:
        """
        检查是否可以接受任务

        Args:
            task_type: 任务类型
            chain: 链
            amount: 金额

        Returns:
            是否可以接受
        """
        # 检查在线
        if not self.online:
            return False

        # 检查额度
        if self.available_quota < amount:
            return False

        # 检查能力
        for cap in self.capabilities:
            if cap.task_type != task_type:
                continue
            if not cap.available:
                continue
            if chain and chain not in cap.supported_chains:
                continue

            # 检查金额限制
            if cap.pricing_model == "fixed":
                if amount < cap.base_price:
                    continue
            elif cap.pricing_model == "percentage":
                # 百分比定价，金额不限
                pass

            return True

        return False

    def get_capability(self, task_type: str) -> Optional[CapabilitySpec]:
        """获取指定类型的能力"""
        for cap in self.capabilities:
            if cap.task_type == task_type:
                return cap
        return None

    def get_price(self, task_type: str, amount: Decimal) -> Decimal:
        """
        获取任务价格

        Args:
            task_type: 任务类型
            amount: 任务金额

        Returns:
            价格
        """
        cap = self.get_capability(task_type)
        if not cap:
            return Decimal("0")

        if cap.pricing_model == "fixed":
            return cap.base_price
        elif cap.pricing_model == "percentage":
            return amount * cap.percentage_rate
        else:
            return cap.base_price
