"""
CryptoMinds Agent 层

Agent 注册、能力描述、语义匹配。
"""

from .capability import AgentCapability, CapabilitySpec
from .registry import AgentRegistry

__all__ = [
    "AgentCapability",
    "CapabilitySpec",
    "AgentRegistry",
]


def init_default_agents():
    """初始化默认 Agent（测试用）"""
    # 这里可以预注册一些测试 Agent
    pass


# 自动初始化
init_default_agents()