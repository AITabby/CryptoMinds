"""
履约记录同步器

将链上事件转换为履约记录，持久化存储到信用分数据库。
"""

import logging
from typing import Dict, List, Optional

from ..credit.models import PerformanceRecord, TaskStatus
from ..credit.store import CreditScoreStore
from .chain_listener import ChainListener, ChainEvent, EventType

logger = logging.getLogger(__name__)


class PerformanceSyncer:
    """
    履约记录同步器

    监听链上事件，转换为履约记录并持久化存储。
    """

    def __init__(
        self,
        listener: ChainListener = None,
        store: CreditScoreStore = None,
    ):
        """
        初始化同步器

        Args:
            listener: 链上监听器
            store: 信用分存储
        """
        self.listener = listener or ChainListener(mock_mode=True)
        self.store = store or CreditScoreStore()

        # 注册回调
        self.listener.register_callback(self._on_event)

    def start(self):
        """启动同步"""
        if not self.listener.connect():
            logger.error("Failed to connect to chain")
            return False

        logger.info("PerformanceSyncer started")
        return True

    def _on_event(self, event: ChainEvent):
        """处理链上事件"""
        logger.debug(f"Received event: {event.event_type.value}")

        escrow_id = event.escrow_id

        # 从数据库加载托管状态
        escrow = self._load_escrow(escrow_id)

        if event.event_type == EventType.ESCROW_CREATED:
            # 创建托管
            escrow = {
                "escrow_id": escrow_id,
                "buyer": event.buyer,
                "seller": event.seller,
                "amount": event.amount,
                "token": event.token,
                "created_at": event.timestamp,
                "status": "pending",
                "tx_hash": event.tx_hash,
                "block_number": event.block_number,
            }
            self._save_escrow(escrow)

        elif event.event_type == EventType.ESCROW_FUNDED:
            # 资金托管
            if escrow:
                escrow["status"] = "funded"
                escrow["fund_tx"] = event.tx_hash
                self._save_escrow(escrow)

        elif event.event_type == EventType.ESCROW_DELIVERED:
            # 提交交付
            if escrow:
                escrow["status"] = "delivered"
                escrow["evidence"] = event.evidence
                escrow["delivered_at"] = event.timestamp
                self._save_escrow(escrow)

        elif event.event_type == EventType.ESCROW_RELEASED:
            # 释放资金（成功）
            if escrow:
                escrow["status"] = "settled"
                escrow["completed_at"] = event.timestamp
                self._save_escrow(escrow)
                self._create_and_save_record(escrow, TaskStatus.SETTLED)

        elif event.event_type == EventType.ESCROW_REFUNDED:
            # 退款
            if escrow:
                escrow["status"] = "refunded"
                escrow["completed_at"] = event.timestamp
                self._save_escrow(escrow)
                self._create_and_save_record(escrow, TaskStatus.REFUNDED)

        elif event.event_type == EventType.DISPUTE_RAISED:
            # 争议
            if escrow:
                escrow["status"] = "disputed"
                escrow["disputed"] = True
                escrow["disputed_at"] = event.timestamp
                self._save_escrow(escrow)

        elif event.event_type == EventType.DISPUTE_RESOLVED:
            # 争议解决
            if escrow:
                resolution = event.resolution
                escrow["resolution"] = resolution
                escrow["completed_at"] = event.timestamp

                if resolution == "buyer_win":
                    escrow["status"] = "refunded"
                    self._save_escrow(escrow)
                    self._create_and_save_record(escrow, TaskStatus.SETTLEMENT_FAILED)
                else:
                    escrow["status"] = "settled"
                    self._save_escrow(escrow)
                    self._create_and_save_record(escrow, TaskStatus.SETTLED)

        elif event.event_type == EventType.TIMEOUT_CLAIMED:
            # 超时
            if escrow:
                escrow["status"] = "timeout"
                escrow["completed_at"] = event.timestamp
                self._save_escrow(escrow)
                self._create_and_save_record(escrow, TaskStatus.TIMEOUT)

    def _load_escrow(self, escrow_id: str) -> Optional[Dict]:
        """从数据库加载托管状态"""
        # 使用专门的托管状态表（简化：复用 performance_records）
        # 实际应该有独立的 escrow_states 表
        # 这里用内存缓存 + 数据库 fallback
        return self._escrows_cache.get(escrow_id)

    def _save_escrow(self, escrow: Dict):
        """保存托管状态到数据库"""
        # 缓存到内存
        self._escrows_cache[escrow["escrow_id"]] = escrow

        # TODO: 持久化到独立的 escrow_states 表

    # 内存缓存（进程重启后需要从数据库恢复）
    _escrows_cache: Dict[str, Dict] = {}

    def _create_and_save_record(
        self,
        escrow: Dict,
        status: TaskStatus,
    ) -> Optional[PerformanceRecord]:
        """
        创建并保存履约记录

        Args:
            escrow: 托管状态
            status: 最终状态

        Returns:
            创建的履约记录
        """
        record = PerformanceRecord(
            record_id=f"perf_{escrow['escrow_id']}",
            task_id=escrow["escrow_id"],
            task_type="escrow",
            buyer_wallet=escrow["buyer"],
            seller_wallet=escrow["seller"],
            seller_agent_id=escrow["seller"],  # 简化：用钱包地址
            chain="bsc",
            amount=escrow["amount"],
            status=status,
            success=status == TaskStatus.SETTLED,
            created_at=escrow["created_at"],
            completed_at=escrow.get("completed_at", 0),
            response_time_ms=self._calc_response_time(escrow),
            payment_tx=escrow.get("fund_tx", ""),
            payment_amount=escrow["amount"],
            evidence=escrow.get("evidence", ""),
            disputed=escrow.get("disputed", False),
            dispute_reason=escrow.get("dispute_reason", ""),
            resolution=escrow.get("resolution", ""),
            # score 字段：链上事件没有，需要后续补充
            # 可以通过验证门评分或买家评价来补充
            score=0.0,  # 待补充
        )

        # 持久化存储
        self.store.save_performance_record(record)
        logger.info(f"Saved performance record: {record.record_id}")

        return record

    def _calc_response_time(self, escrow: Dict) -> int:
        """计算响应时间（毫秒）"""
        created = escrow.get("created_at", 0)
        delivered = escrow.get("delivered_at", 0)
        if created and delivered:
            return (delivered - created) * 1000
        return 0

    def sync_history(self, from_block: int = None, limit: int = 1000):
        """
        同步历史数据

        Args:
            from_block: 起始区块
            limit: 最大事件数
        """
        events = self.listener.fetch_events(from_block=from_block, limit=limit)
        logger.info(f"Synced {len(events)} historical events")

        for event in events:
            self._on_event(event)

    def get_records_for_agent(self, agent_id: str) -> List[PerformanceRecord]:
        """
        从数据库获取 Agent 的履约记录

        Args:
            agent_id: Agent ID 或钱包地址
        """
        return self.store.get_performance_records(agent_id=agent_id)

    def get_records_for_wallet(self, wallet: str) -> List[PerformanceRecord]:
        """
        从数据库获取钱包相关的履约记录

        Args:
            wallet: 钱包地址
        """
        return self.store.get_performance_records(wallet=wallet)
