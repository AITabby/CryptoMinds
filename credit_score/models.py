"""
SACRED 信用分数据模型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import hashlib
import json
import time

from .config import DIMENSION_MAX, TOTAL_MAX, GRADE_THRESHOLDS


class TaskStatus(Enum):
    """履约记录状态（模块自治副本，不依赖主项目）"""
    PENDING = "pending"
    EXECUTING = "executing"
    VERIFIED = "verified"
    SETTLED = "settled"
    SETTLEMENT_FAILED = "settlement_failed"
    FAILED = "failed"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    TIMEOUT = "timeout"

    @classmethod
    def from_value(cls, value: str) -> "TaskStatus":
        """从字符串值构造，未知值默认为 FAILED"""
        for member in cls:
            if member.value == value:
                return member
        return cls.FAILED


@dataclass
class PerformanceRecord:
    """履约记录（模块自治副本，仅含 calculator 所需字段）"""
    record_id: str = ""
    task_id: str = ""
    task_type: str = ""
    buyer_wallet: str = ""
    seller_wallet: str = ""
    seller_agent_id: str = ""
    chain: str = ""
    amount: str = "0"
    status: TaskStatus = TaskStatus.PENDING
    success: bool = False
    score: float = 0.0
    created_at: int = 0
    completed_at: int = 0
    response_time_ms: int = 0
    payment_tx: str = ""
    payment_amount: str = "0"
    evidence: str = ""
    disputed: bool = False
    dispute_reason: str = ""
    resolution: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "PerformanceRecord":
        """从字典构造，自动转换 status 字符串为 TaskStatus"""
        status_val = data.get("status", "pending")
        status = TaskStatus.from_value(status_val) if isinstance(status_val, str) else status_val
        return cls(
            record_id=data.get("record_id", ""),
            task_id=data.get("task_id", ""),
            task_type=data.get("task_type", ""),
            buyer_wallet=data.get("buyer_wallet", ""),
            seller_wallet=data.get("seller_wallet", ""),
            seller_agent_id=data.get("seller_agent_id", ""),
            chain=data.get("chain", ""),
            amount=str(data.get("amount", "0")),
            status=status,
            success=bool(data.get("success", False)),
            score=float(data.get("score", 0.0)),
            created_at=int(data.get("created_at", 0)),
            completed_at=int(data.get("completed_at", 0)),
            response_time_ms=int(data.get("response_time_ms", 0)),
            payment_tx=data.get("payment_tx", ""),
            payment_amount=str(data.get("payment_amount", "0")),
            evidence=data.get("evidence", ""),
            disputed=bool(data.get("disputed", False)),
            dispute_reason=data.get("dispute_reason", ""),
            resolution=data.get("resolution", ""),
        )


class CreditGrade(Enum):
    """信用等级"""
    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    CCC = "CCC"
    CC = "CC"
    C = "C"

    @classmethod
    def from_score(cls, score: float) -> "CreditGrade":
        """根据总分确定等级"""
        for grade, threshold in GRADE_THRESHOLDS:
            if score >= threshold:
                return cls(grade)
        return cls.C


@dataclass
class DimensionScore:
    """单维度评分"""
    dimension: str          # S/A/C/R/E
    name: str               # Stability/Activity/Creditworthiness/Reliability/Ecosystem
    raw_score: float = 0.0  # 0-DIMENSION_MAX
    weighted_score: float = 0.0  # 衰减后加权分
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "dimension": self.dimension,
            "name": self.name,
            "score": round(self.weighted_score, 1),
            "max": DIMENSION_MAX,
            "components": {k: round(v, 1) for k, v in self.components.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DimensionScore":
        return cls(
            dimension=data.get("dimension", ""),
            name=data.get("name", ""),
            raw_score=data.get("raw_score", 0.0),
            weighted_score=data.get("weighted_score", 0.0),
            components=data.get("components", {}),
        )


@dataclass
class SacredScore:
    """SACRED 五维信用分"""
    agent_id: str = ""
    wallet: str = ""

    stability: DimensionScore = field(default_factory=lambda: DimensionScore("S", "Stability"))
    activity: DimensionScore = field(default_factory=lambda: DimensionScore("A", "Activity"))
    creditworthiness: DimensionScore = field(default_factory=lambda: DimensionScore("C", "Creditworthiness"))
    reliability: DimensionScore = field(default_factory=lambda: DimensionScore("R", "Reliability"))
    ecosystem: DimensionScore = field(default_factory=lambda: DimensionScore("E", "Ecosystem"))

    total_score: float = 0.0
    grade: str = "C"
    is_cold_start: bool = False
    calculated_at: int = 0
    snapshot_hash: str = ""

    @property
    def dimensions(self) -> Dict[str, DimensionScore]:
        return {
            "S": self.stability,
            "A": self.activity,
            "C": self.creditworthiness,
            "R": self.reliability,
            "E": self.ecosystem,
        }

    def compute_total(self) -> float:
        """计算总分"""
        total = sum(d.weighted_score for d in self.dimensions.values())
        self.total_score = min(TOTAL_MAX, max(0.0, round(total, 1)))
        self.grade = CreditGrade.from_score(self.total_score).value
        return self.total_score

    def compute_hash(self) -> str:
        """计算结果快照哈希，防篡改"""
        content = json.dumps({
            "agent_id": self.agent_id,
            "wallet": self.wallet,
            "total_score": self.total_score,
            "grade": self.grade,
            "dimensions": {k: round(v.weighted_score, 2) for k, v in self.dimensions.items()},
            "calculated_at": self.calculated_at,
        }, sort_keys=True)
        self.snapshot_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.snapshot_hash

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "wallet": self.wallet,
            "total_score": self.total_score,
            "grade": self.grade,
            "is_cold_start": self.is_cold_start,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "calculated_at": self.calculated_at,
            "snapshot_hash": self.snapshot_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SacredScore":
        dims = data.get("dimensions", {})
        return cls(
            agent_id=data.get("agent_id", ""),
            wallet=data.get("wallet", ""),
            stability=DimensionScore.from_dict(dims.get("S", {})),
            activity=DimensionScore.from_dict(dims.get("A", {})),
            creditworthiness=DimensionScore.from_dict(dims.get("C", {})),
            reliability=DimensionScore.from_dict(dims.get("R", {})),
            ecosystem=DimensionScore.from_dict(dims.get("E", {})),
            total_score=data.get("total_score", 0.0),
            grade=data.get("grade", "C"),
            is_cold_start=data.get("is_cold_start", False),
            calculated_at=data.get("calculated_at", 0),
            snapshot_hash=data.get("snapshot_hash", ""),
        )


@dataclass
class QueryAuthorization:
    """查询授权"""
    auth_id: str = ""
    agent_id: str = ""      # 被查询的 Agent
    querier_id: str = ""    # 查询方
    signature: str = ""     # Agent 签名
    expires_at: int = 0
    created_at: int = 0

    @property
    def is_expired(self) -> bool:
        return int(time.time()) >= self.expires_at

    def to_dict(self) -> Dict:
        return {
            "auth_id": self.auth_id,
            "agent_id": self.agent_id,
            "querier_id": self.querier_id,
            "signature": self.signature,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


@dataclass
class ScoreHistoryEntry:
    """信用分历史记录"""
    agent_id: str = ""
    score: float = 0.0
    grade: str = ""
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    calculated_at: int = 0

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "score": self.score,
            "grade": self.grade,
            "dimension_scores": self.dimension_scores,
            "calculated_at": self.calculated_at,
        }
