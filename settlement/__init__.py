"""
CryptoMinds 结算通道层

多链、多代币、多协议的统一结算抽象。
"""

from .base import SettlementChannel, PaymentRequest, PaymentResult
from .registry import ChannelRegistry
from .channels import BSCNativeChannel, ETHNativeChannel, SOLNativeChannel, MockChannel

__all__ = [
    "SettlementChannel",
    "PaymentRequest",
    "PaymentResult",
    "ChannelRegistry",
    "BSCNativeChannel",
    "ETHNativeChannel",
    "SOLNativeChannel",
    "MockChannel",
]


def init_default_channels():
    """初始化默认通道"""
    import os
    test_mode = os.getenv("SETTLEMENT_TEST_MODE", "false").lower() == "true"

    if not ChannelRegistry.get("bsc-native"):
        ChannelRegistry.register(BSCNativeChannel(test_mode=test_mode))

    if not ChannelRegistry.get("eth-native"):
        ChannelRegistry.register(ETHNativeChannel(test_mode=test_mode))

    if not ChannelRegistry.get("sol-native"):
        ChannelRegistry.register(SOLNativeChannel(test_mode=test_mode))

    if not ChannelRegistry.get("mock"):
        ChannelRegistry.register(MockChannel())


# 自动初始化
init_default_channels()
