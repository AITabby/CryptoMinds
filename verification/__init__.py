"""
CryptoMinds 验证门层

任务完成验证的抽象层，支持多任务类型、多链验证。
"""

from .base import VerificationGate, VerificationResult
from .registry import GateRegistry

__all__ = [
    "VerificationGate",
    "VerificationResult",
    "GateRegistry",
]


def init_default_gates():
    """初始化默认验证门"""
    from .gates.token_delivery import TokenDeliveryGate
    from .gates.data_delivery import DataDeliveryGate
    from .gates.compute_result import ComputeResultGate
    from .gates.signal_content import SignalStreamGate, ContentDeliveryGate

    if not GateRegistry.get("token_delivery"):
        GateRegistry.register(TokenDeliveryGate())

    if not GateRegistry.get("data_delivery"):
        GateRegistry.register(DataDeliveryGate())

    if not GateRegistry.get("compute_result"):
        GateRegistry.register(ComputeResultGate())

    if not GateRegistry.get("signal_stream"):
        GateRegistry.register(SignalStreamGate())

    if not GateRegistry.get("content_delivery"):
        GateRegistry.register(ContentDeliveryGate())


# 自动初始化
init_default_gates()
