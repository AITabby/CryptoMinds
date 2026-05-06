"""
链上事件监听器

监听 BSC 链上托管合约事件，采集履约数据。
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """链上事件类型"""
    ESCROW_CREATED = "EscrowCreated"
    ESCROW_FUNDED = "EscrowFunded"
    ESCROW_DELIVERED = "EscrowDelivered"
    ESCROW_RELEASED = "EscrowReleased"
    ESCROW_REFUNDED = "EscrowRefunded"
    DISPUTE_RAISED = "DisputeRaised"
    DISPUTE_RESOLVED = "DisputeResolved"
    TIMEOUT_CLAIMED = "TimeoutClaimed"


@dataclass
class ChainEvent:
    """链上事件"""
    event_type: EventType
    tx_hash: str
    block_number: int
    timestamp: int
    escrow_id: str
    buyer: str = ""
    seller: str = ""
    amount: str = "0"
    token: str = ""
    resolution: str = ""  # buyer_win / seller_win
    evidence: str = ""


class ChainListener:
    """
    链上事件监听器

    支持 Web3 或模拟模式。
    """

    # 托管合约地址（BSC Testnet）
    ESCROW_CONTRACT = "0xe9C878845F7299C00Ff6465B02f43De2a1b49b62"

    # 事件签名（keccak256 哈希）
    # 实际部署时需要根据合约 ABI 计算真实哈希
    # 示例: keccak256("EscrowCreated(bytes32,address,address,uint256,address)")
    EVENT_SIGNATURES: Dict[str, EventType] = {
        # EscrowCreated(bytes32 indexed escrowId, address buyer,
        #               address seller, uint256 amount, address token)
        "0xa9059cbb00000000000000000000000000000000000000000000000000000000":
            EventType.ESCROW_CREATED,
        # EscrowFunded(bytes32 indexed escrowId, bytes32 fundTxHash)
        "0x23b872dd00000000000000000000000000000000000000000000000000000000":
            EventType.ESCROW_FUNDED,
        # EscrowDelivered(bytes32 indexed escrowId, bytes evidence)
        "0x095ea7b300000000000000000000000000000000000000000000000000000000":
            EventType.ESCROW_DELIVERED,
        # EscrowReleased(bytes32 indexed escrowId)
        "0x42842e0e00000000000000000000000000000000000000000000000000000000":
            EventType.ESCROW_RELEASED,
        # EscrowRefunded(bytes32 indexed escrowId)
        "0xba0a50a000000000000000000000000000000000000000000000000000000000":
            EventType.ESCROW_REFUNDED,
        # DisputeRaised(bytes32 indexed escrowId, address raiser, bytes reason)
        "0x8f9f4b6300000000000000000000000000000000000000000000000000000000":
            EventType.DISPUTE_RAISED,
        # DisputeResolved(bytes32 indexed escrowId, uint8 resolution)
        "0x3f4ba83a00000000000000000000000000000000000000000000000000000000":
            EventType.DISPUTE_RESOLVED,
        # TimeoutClaimed(bytes32 indexed escrowId)
        "0x5c975abb00000000000000000000000000000000000000000000000000000000":
            EventType.TIMEOUT_CLAIMED,
    }

    def __init__(
        self,
        rpc_url: str = None,
        contract_address: str = None,
        mock_mode: bool = False,
    ):
        """
        初始化监听器

        Args:
            rpc_url: BSC RPC URL (默认使用公共节点)
            contract_address: 托管合约地址
            mock_mode: 模拟模式（不连接真实链）
        """
        self.rpc_url = rpc_url or "https://data-seed-prebsc-1-s1.binance.org:8545"
        self.contract_address = contract_address or self.ESCROW_CONTRACT
        self.mock_mode = mock_mode
        self._web3 = None
        self._contract = None
        self._last_block = 0
        self._callbacks: List[Callable] = []

    def connect(self) -> bool:
        """连接到链"""
        if self.mock_mode:
            logger.info("ChainListener running in mock mode")
            return True

        try:
            from web3 import Web3
            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self._web3.is_connected():
                logger.error(f"Failed to connect to {self.rpc_url}")
                return False

            logger.info(f"Connected to BSC, block: {self._web3.eth.block_number}")
            return True
        except ImportError:
            logger.warning("web3 not installed, using mock mode")
            self.mock_mode = True
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def register_callback(self, callback: Callable[[ChainEvent], None]):
        """注册事件回调"""
        self._callbacks.append(callback)

    def _notify_callbacks(self, event: ChainEvent):
        """通知所有回调"""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def fetch_events(
        self,
        from_block: int = None,
        to_block: int = None,
        limit: int = 1000,
    ) -> List[ChainEvent]:
        """
        获取事件

        Args:
            from_block: 起始区块
            to_block: 结束区块
            limit: 最大事件数
        """
        if self.mock_mode:
            return self._fetch_mock_events(limit)

        if self._web3 is None:
            return []

        from_block = from_block or self._last_block
        to_block = to_block or self._web3.eth.block_number

        events = []

        try:
            logs = self._web3.eth.get_logs({
                "address": self.contract_address,
                "fromBlock": from_block,
                "toBlock": to_block,
            })

            for log in logs[:limit]:
                event = self._parse_log(log)
                if event:
                    events.append(event)
                    self._notify_callbacks(event)

            self._last_block = to_block
        except Exception as e:
            logger.error(f"Error fetching events: {e}")

        return events

    def _parse_log(self, log) -> Optional[ChainEvent]:
        """
        解析日志为事件

        根据 topics[0] 匹配事件类型，从区块获取真实时间戳。
        """
        try:
            # 从 topics[0] 获取事件签名哈希
            topic0 = log["topics"][0].hex() if log.get("topics") else ""

            # 匹配事件类型
            event_type = self._match_event_type(topic0)
            if event_type is None:
                logger.debug(f"Unknown event signature: {topic0}")
                return None

            # 从区块获取真实时间戳
            block = self._web3.eth.get_block(log["blockNumber"])
            timestamp = block["timestamp"]

            # 解码事件数据（根据事件类型）
            return self._decode_event(event_type, log, timestamp)
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None

    def _match_event_type(self, topic_hash: str) -> Optional[EventType]:
        """
        根据事件签名哈希匹配事件类型

        Args:
            topic_hash: topics[0] 的哈希值（完整 66 字符）

        Note:
            实际部署时需要用 Web3.keccak(text) 计算真实签名哈希。
            当前使用占位哈希，上线前需替换为真实值。
        """
        # 精确匹配完整哈希（66 字符，含 0x 前缀）
        if topic_hash in self.EVENT_SIGNATURES:
            return self.EVENT_SIGNATURES[topic_hash]

        # 兼容：如果哈希长度不足，尝试前缀匹配（仅用于测试）
        for sig, et in self.EVENT_SIGNATURES.items():
            if topic_hash == sig or topic_hash.startswith(sig[:18]):
                return et

        return None

    def _decode_event(
        self,
        event_type: EventType,
        log,
        timestamp: int,
    ) -> ChainEvent:
        """
        解码事件数据

        根据事件类型解析 indexed 和 non-indexed 参数。
        """
        tx_hash = log["transactionHash"].hex()
        block_number = log["blockNumber"]

        # 基础字段
        escrow_id = ""
        buyer = ""
        seller = ""
        amount = "0"
        token = ""
        resolution = ""
        evidence = ""

        topics = log.get("topics", [])
        data = log.get("data", "0x")

        # 根据事件类型解析
        if event_type == EventType.ESCROW_CREATED:
            # EscrowCreated(bytes32 indexed escrowId, address buyer,
            #               address seller, uint256 amount, address token)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()
            # buyer, seller, amount, token 在 data 中（非 indexed）
            # 需要 ABI 解码，这里简化处理
            if data and len(data) > 2:
                # 简化：假设 data 包含地址和数值
                pass

        elif event_type == EventType.ESCROW_FUNDED:
            # EscrowFunded(bytes32 indexed escrowId, bytes32 fundTxHash)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()

        elif event_type == EventType.ESCROW_DELIVERED:
            # EscrowDelivered(bytes32 indexed escrowId, bytes evidence)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()
            evidence = data

        elif event_type == EventType.ESCROW_RELEASED:
            # EscrowReleased(bytes32 indexed escrowId)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()

        elif event_type == EventType.ESCROW_REFUNDED:
            # EscrowRefunded(bytes32 indexed escrowId)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()

        elif event_type == EventType.DISPUTE_RAISED:
            # DisputeRaised(bytes32 indexed escrowId, address raiser, bytes reason)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()

        elif event_type == EventType.DISPUTE_RESOLVED:
            # DisputeResolved(bytes32 indexed escrowId, uint8 resolution)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()
            # resolution: 0=buyer_win, 1=seller_win
            if data and len(data) > 2:
                resolution_val = int(data[-2:], 16)
                resolution = "buyer_win" if resolution_val == 0 else "seller_win"

        elif event_type == EventType.TIMEOUT_CLAIMED:
            # TimeoutClaimed(bytes32 indexed escrowId)
            if len(topics) >= 2:
                escrow_id = topics[1].hex()

        return ChainEvent(
            event_type=event_type,
            tx_hash=tx_hash,
            block_number=block_number,
            timestamp=timestamp,
            escrow_id=escrow_id,
            buyer=buyer,
            seller=seller,
            amount=amount,
            token=token,
            resolution=resolution,
            evidence=evidence,
        )

    def _fetch_mock_events(self, limit: int) -> List[ChainEvent]:
        """模拟模式：返回空列表"""
        return []

    def listen_loop(self, poll_interval: int = 12):
        """
        持续监听循环

        Args:
            poll_interval: 轮询间隔（秒）
        """
        logger.info(f"Starting listen loop, interval={poll_interval}s")

        while True:
            try:
                events = self.fetch_events()
                if events:
                    logger.info(f"Fetched {len(events)} events")
            except Exception as e:
                logger.error(f"Listen error: {e}")

            time.sleep(poll_interval)
