"""
结算通道注册表

管理所有可用的结算通道，支持动态注册和查询。
"""

from typing import Dict, List, Optional
from .base import SettlementChannel


class ChannelRegistry:
    """
    结算通道注册表

    用法:
        # 注册通道
        ChannelRegistry.register(BSCNativeChannel())
        ChannelRegistry.register(ETHNativeChannel())

        # 获取通道
        channel = ChannelRegistry.get("bsc-native")

        # 查询支持的链
        channels = ChannelRegistry.list_for_chain("bsc")

        # 列出所有通道
        all_channels = ChannelRegistry.list_all()
    """

    _channels: Dict[str, SettlementChannel] = {}

    @classmethod
    def register(cls, channel: SettlementChannel) -> None:
        """注册结算通道"""
        if not channel.channel_id:
            raise ValueError("通道必须定义 channel_id")
        cls._channels[channel.channel_id] = channel

    @classmethod
    def unregister(cls, channel_id: str) -> bool:
        """注销结算通道"""
        if channel_id in cls._channels:
            del cls._channels[channel_id]
            return True
        return False

    @classmethod
    def get(cls, channel_id: str) -> Optional[SettlementChannel]:
        """获取指定通道"""
        return cls._channels.get(channel_id)

    @classmethod
    def get_or_default(cls, channel_id: str, default_chain: str = "bsc") -> Optional[SettlementChannel]:
        """
        获取通道，如果不存在则返回指定链的默认通道

        默认通道命名规则: {chain}-native
        """
        channel = cls._channels.get(channel_id)
        if channel:
            return channel
        return cls._channels.get(f"{default_chain}-native")

    @classmethod
    def list_for_chain(cls, chain: str) -> List[SettlementChannel]:
        """列出指定链的所有通道"""
        return [c for c in cls._channels.values() if c.chain == chain]

    @classmethod
    def list_for_token(cls, token: str) -> List[SettlementChannel]:
        """列出支持指定代币的所有通道"""
        return [c for c in cls._channels.values() if c.token.lower() == token.lower()]

    @classmethod
    def list_all(cls) -> List[Dict]:
        """列出所有通道信息"""
        return [c.to_dict() for c in cls._channels.values()]

    @classmethod
    def list_supported_chains(cls) -> List[str]:
        """列出所有支持的链"""
        return list(set(c.chain for c in cls._channels.values()))

    @classmethod
    def list_supported_tokens(cls, chain: str) -> List[str]:
        """列出指定链支持的所有代币"""
        return list(set(c.token for c in cls._channels.values() if c.chain == chain))

    @classmethod
    def clear(cls) -> None:
        """清空所有注册（测试用）"""
        cls._channels.clear()


# 导入 Dict 类型
from typing import Dict
