"""
履约记录同步器

将链上事件转换为履约记录，持久化存储到统一数据库。
"""

import logging
from typing import List, Optional

try:
    from credit.models import PerformanceRecord, TaskStatus
    from collector.chain_listener import ChainListener, ChainEvent, EventType
except ImportError:
    from ..credit.models import PerformanceRecord, TaskStatus
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
        store=None,
    ):
        """
        初始化同步器

        Args:
            listener: 链上监听器
            store: 统一存储实例
        """
        self.listener = listener or ChainListener(mock_mode=True)
        self.store = store or self._default_store()

        # 注册回调
        self.listener.register_callback(self._on_event)

    def _default_store(self):
        """获取默认存储"""
        from store import UnifiedStore
        return UnifiedStore()

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
        escrow = self.store.get_escrow(escrow_id)

        if event.event_type == EventType.ESCROW_CREATED:
            # 创建托管
            escrow = {
                "escrow_id": escrow_id,
                "buyer": event.buyer,
                "seller": event.seller,
                "amount": event.amount,
                "token": event.token,
                "status": "pending",
                "created_at": event.timestamp,
                "fund_tx": event.tx_hash,
            }
            self.store.update_escrow_status(escrow_id, "pending")

        elif event.event_type == EventType.ESCROW_FUNDED:
            # 资金托管
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "funded",
                    fund_tx=event.tx_hash,
                    funded_at=event.timestamp,
                )

        elif event.event_type == EventType.ESCROW_DELIVERED:
            # 提交交付
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "delivered",
                    evidence=event.evidence,
                    delivered_at=event.timestamp,
                )

        elif event.event_type == EventType.ESCROW_RELEASED:
            # 释放资金（成功）
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "settled",
                    completed_at=event.timestamp,
                )
                self._create_and_save_record(escrow_id, TaskStatus.SETTLED)

        elif event.event_type == EventType.ESCROW_REFUNDED:
            # 退款
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "refunded",
                    completed_at=event.timestamp,
                )
                self._create_and_save_record(escrow_id, TaskStatus.REFUNDED)

        elif event.event_type == EventType.DISPUTE_RAISED:
            # 争议
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "disputed",
                    disputed=True,
                    dispute_reason=event.evidence,
                )

        elif event.event_type == EventType.DISPUTE_RESOLVED:
            # 争议解决
            if escrow:
                resolution = event.resolution
                if resolution == "buyer_win":
                    self.store.update_escrow_status(
                        escrow_id, "refunded",
                        resolution="buyer_win",
                        completed_at=event.timestamp,
                    )
                    self._create_and_save_record(escrow_id, TaskStatus.SETTLEMENT_FAILED)
                else:
                    self.store.update_escrow_status(
                        escrow_id, "settled",
                        resolution="seller_win",
                        completed_at=event.timestamp,
                    )
                    self._create_and_save_record(escrow_id, TaskStatus.SETTLED)

        elif event.event_type == EventType.TIMEOUT_CLAIMED:
            # 超时
            if escrow:
                self.store.update_escrow_status(
                    escrow_id, "timeout",
                    completed_at=event.timestamp,
                )
                self._create_and_save_record(escrow_id, TaskStatus.TIMEOUT)

    def _create_and_save_record(
        self,
        escrow_id: str,
        status: TaskStatus,
    ) -> Optional[PerformanceRecord]:
        """
        创建并保存履约记录

        Args:
            escrow_id: 托管 ID
            status: 最终状态

        Returns:
            创建的履约记录
        """
        escrow = self.store.get_escrow(escrow_id)
        if not escrow:
            return None

        # 计算响应时间
        response_time = 0
        if escrow.get("delivered_at") and escrow.get("created_at"):
            response_time = (escrow["delivered_at"] - escrow["created_at"]) * 1000

        record = PerformanceRecord(
            record_id=f"perf_{escrow_id}",
            task_id=escrow_id,
            task_type="escrow",
            buyer_wallet=escrow["buyer"],
            seller_wallet=escrow["seller"],
            seller_agent_id=escrow["seller"],
            chain="bsc",
            amount=escrow["amount"],
            status=status,
            success=status == TaskStatus.SETTLED,
            created_at=escrow["created_at"],
            completed_at=escrow.get("completed_at", 0),
            response_time_ms=response_time,
            payment_tx=escrow.get("fund_tx", ""),
            payment_amount=escrow["amount"],
            evidence=escrow.get("evidence", ""),
            disputed=escrow.get("disputed", False),
            dispute_reason=escrow.get("dispute_reason", ""),
            resolution=escrow.get("resolution", ""),
            # score: 链上事件无此字段，默认 0.5（中性）
            # 后续可通过验证门评分或买家评价补充
            score=0.5,
        )

        # 持久化存储
        self.store.save_performance_record(record)
        logger.info(f"Saved performance record: {record.record_id}")

        return record

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
