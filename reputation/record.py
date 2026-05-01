"""
履约记录

记录每次任务执行的完整信息，作为信誉计算的基础。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum
import time
import hashlib


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    VERIFIED = "verified"        # 验证通过
    SETTLED = "settled"          # 验证且结算完成
    SETTLEMENT_FAILED = "settlement_failed"  # 验证通过但结算失败
    FAILED = "failed"            # 执行失败
    DISPUTED = "disputed"        # 发生争议
    REFUNDED = "refunded"        # 已退款
    TIMEOUT = "timeout"          # 超时


@dataclass
class PerformanceRecord:
    """
    履约记录

    记录一次任务执行的完整信息。
    """

    # 基本信息
    record_id: str = ""
    task_id: str = ""
    task_type: str = ""

    # 参与方
    buyer_wallet: str = ""
    seller_wallet: str = ""
    seller_agent_id: str = ""

    # 任务参数
    chain: str = ""
    amount: Decimal = Decimal("0")
    token_address: str = ""

    # 执行结果
    status: TaskStatus = TaskStatus.PENDING
    success: bool = False
    score: float = 0.0              # 验证门评分 0-1

    # 时间
    created_at: int = field(default_factory=lambda: int(time.time()))
    started_at: int = 0
    completed_at: int = 0
    response_time_ms: int = 0       # 响应时间（毫秒）

    # 结算
    channel_id: str = ""
    payment_tx: str = ""
    payment_amount: Decimal = Decimal("0")

    # 验证证据
    evidence: Dict = field(default_factory=dict)

    # 争议
    disputed: bool = False
    dispute_reason: str = ""
    resolution: str = ""            # buyer_win, seller_win, split

    def to_dict(self) -> Dict:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "buyer_wallet": self.buyer_wallet,
            "seller_wallet": self.seller_wallet,
            "seller_agent_id": self.seller_agent_id,
            "chain": self.chain,
            "amount": str(self.amount),
            "token_address": self.token_address,
            "status": self.status.value,
            "success": self.success,
            "score": self.score,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "response_time_ms": self.response_time_ms,
            "channel_id": self.channel_id,
            "payment_tx": self.payment_tx,
            "payment_amount": str(self.payment_amount),
            "evidence": self.evidence,
            "disputed": self.disputed,
            "dispute_reason": self.dispute_reason,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PerformanceRecord":
        """从字典创建"""
        return cls(
            record_id=data.get("record_id", ""),
            task_id=data.get("task_id", ""),
            task_type=data.get("task_type", ""),
            buyer_wallet=data.get("buyer_wallet", ""),
            seller_wallet=data.get("seller_wallet", ""),
            seller_agent_id=data.get("seller_agent_id", ""),
            chain=data.get("chain", ""),
            amount=Decimal(str(data.get("amount", 0))),
            token_address=data.get("token_address", ""),
            status=TaskStatus(data.get("status", "pending")),
            success=data.get("success", False),
            score=data.get("score", 0.0),
            created_at=data.get("created_at", 0),
            started_at=data.get("started_at", 0),
            completed_at=data.get("completed_at", 0),
            response_time_ms=data.get("response_time_ms", 0),
            channel_id=data.get("channel_id", ""),
            payment_tx=data.get("payment_tx", ""),
            payment_amount=Decimal(str(data.get("payment_amount", 0))),
            evidence=data.get("evidence", {}),
            disputed=data.get("disputed", False),
            dispute_reason=data.get("dispute_reason", ""),
            resolution=data.get("resolution", ""),
        )

    @classmethod
    def create(
        cls,
        task_id: str,
        task_type: str,
        buyer_wallet: str,
        seller_wallet: str,
        seller_agent_id: str,
        chain: str,
        amount: Decimal,
        **kwargs
    ) -> "PerformanceRecord":
        """创建新记录"""
        record_id = hashlib.sha256(
            f"{task_id}{time.time()}".encode()
        ).hexdigest()[:32]

        return cls(
            record_id=record_id,
            task_id=task_id,
            task_type=task_type,
            buyer_wallet=buyer_wallet,
            seller_wallet=seller_wallet,
            seller_agent_id=seller_agent_id,
            chain=chain,
            amount=amount,
            **kwargs
        )


class RecordStore:
    """
    履约记录存储

    支持内存存储和文件存储。
    """

    def __init__(self, storage_type: str = "memory", path: str = None):
        self.storage_type = storage_type
        self.path = path
        self._records: Dict[str, PerformanceRecord] = {}
        self._seller_index: Dict[str, List[str]] = {}  # seller_wallet -> [record_ids]
        self._buyer_index: Dict[str, List[str]] = {}   # buyer_wallet -> [record_ids]

    # ── CRUD ─────────────────────────────────────────

    def save(self, record: PerformanceRecord) -> None:
        """保存记录"""
        self._records[record.record_id] = record

        # 更新索引
        if record.seller_wallet:
            if record.seller_wallet not in self._seller_index:
                self._seller_index[record.seller_wallet] = []
            self._seller_index[record.seller_wallet].append(record.record_id)

        if record.buyer_wallet:
            if record.buyer_wallet not in self._buyer_index:
                self._buyer_index[record.buyer_wallet] = []
            self._buyer_index[record.buyer_wallet].append(record.record_id)

        # 文件存储
        if self.storage_type == "file" and self.path:
            self._save_to_file()

    def get(self, record_id: str) -> Optional[PerformanceRecord]:
        """获取记录"""
        return self._records.get(record_id)

    def get_by_task(self, task_id: str) -> Optional[PerformanceRecord]:
        """通过任务 ID 获取记录"""
        for record in self._records.values():
            if record.task_id == task_id:
                return record
        return None

    def get_by_seller(
        self,
        seller_wallet: str,
        limit: int = 100,
        status: TaskStatus = None
    ) -> List[PerformanceRecord]:
        """获取卖家的记录"""
        record_ids = self._seller_index.get(seller_wallet, [])
        records = [self._records[rid] for rid in record_ids if rid in self._records]

        # 过滤状态
        if status:
            records = [r for r in records if r.status == status]

        # 按时间排序
        records.sort(key=lambda r: r.created_at, reverse=True)

        return records[:limit]

    def get_by_buyer(
        self,
        buyer_wallet: str,
        limit: int = 100
    ) -> List[PerformanceRecord]:
        """获取买家的记录"""
        record_ids = self._buyer_index.get(buyer_wallet, [])
        records = [self._records[rid] for rid in record_ids if rid in self._records]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    # ── 统计 ─────────────────────────────────────────

    def count_by_seller(self, seller_wallet: str) -> Dict:
        """统计卖家记录"""
        records = self.get_by_seller(seller_wallet, limit=10000)

        total = len(records)
        completed = len([r for r in records if r.status == TaskStatus.SETTLED])
        failed = len([r for r in records if r.status in (TaskStatus.FAILED, TaskStatus.SETTLEMENT_FAILED)])
        disputed = len([r for r in records if r.disputed])

        total_volume = sum(r.payment_amount for r in records if r.success)
        avg_score = sum(r.score for r in records if r.success) / completed if completed > 0 else 0

        response_times = [r.response_time_ms for r in records if r.response_time_ms > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "disputed": disputed,
            "success_rate": completed / total if total > 0 else 0,
            "total_volume": str(total_volume),
            "avg_score": avg_score,
            "avg_response_time_ms": int(avg_response_time),
        }

    # ── 文件存储 ─────────────────────────────────────

    def _save_to_file(self):
        """保存到文件"""
        import json
        from pathlib import Path

        if not self.path:
            return

        data = {
            "records": [r.to_dict() for r in self._records.values()],
        }

        Path(self.path).write_text(json.dumps(data, indent=2))

    def _load_from_file(self):
        """从文件加载"""
        import json
        from pathlib import Path

        if not self.path or not Path(self.path).exists():
            return

        data = json.loads(Path(self.path).read_text())

        for r in data.get("records", []):
            record = PerformanceRecord.from_dict(r)
            self._records[record.record_id] = record

            # 重建索引
            if record.seller_wallet:
                if record.seller_wallet not in self._seller_index:
                    self._seller_index[record.seller_wallet] = []
                self._seller_index[record.seller_wallet].append(record.record_id)

            if record.buyer_wallet:
                if record.buyer_wallet not in self._buyer_index:
                    self._buyer_index[record.buyer_wallet] = []
                self._buyer_index[record.buyer_wallet].append(record.record_id)

    # ── 清理 ─────────────────────────────────────────

    def clear(self):
        """清空所有记录（测试用）"""
        self._records.clear()
        self._seller_index.clear()
        self._buyer_index.clear()
