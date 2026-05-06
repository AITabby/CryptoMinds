"""
统一数据存储层

所有数据存储到单一 SQLite 数据库，包括：
- 托管状态 (escrows)
- 争议记录 (disputes)
- 履约记录 (performance_records)
- 信用分快照 (sacred_scores)
- 查询授权 (query_authorizations)
"""

import json
import os
import sqlite3
import time
import uuid
from typing import Dict, List, Optional

# 默认数据库路径
DEFAULT_DB_PATH = os.getenv("CRYPTOMINDS_DB_PATH", "cryptominds.db")


class UnifiedStore:
    """
    统一数据存储

    单一 SQLite 数据库，WAL 模式，支持高并发。
    """

    def __init__(self, db_path: str = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """创建所有表"""
        conn = self._connect()
        try:
            conn.executescript("""
                -- 托管表
                CREATE TABLE IF NOT EXISTS escrows (
                    escrow_id TEXT PRIMARY KEY NOT NULL,
                    buyer TEXT NOT NULL,
                    seller TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    token TEXT DEFAULT 'BNB',
                    timeout INTEGER DEFAULT 86400,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    funded_at INTEGER DEFAULT 0,
                    delivered_at INTEGER DEFAULT 0,
                    completed_at INTEGER DEFAULT 0,
                    fund_tx TEXT DEFAULT '',
                    delivery_proof TEXT DEFAULT '',
                    evidence TEXT DEFAULT '',
                    disputed INTEGER DEFAULT 0,
                    dispute_reason TEXT DEFAULT '',
                    resolution TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_escrow_buyer ON escrows(buyer);
                CREATE INDEX IF NOT EXISTS idx_escrow_seller ON escrows(seller);
                CREATE INDEX IF NOT EXISTS idx_escrow_status ON escrows(status);

                -- 争议表
                CREATE TABLE IF NOT EXISTS disputes (
                    dispute_id TEXT PRIMARY KEY NOT NULL,
                    escrow_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence TEXT DEFAULT '{}',
                    evidence_list TEXT DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    arbitrators TEXT DEFAULT '[]',
                    votes TEXT DEFAULT '[]',
                    result TEXT DEFAULT '',
                    resolution_reason TEXT DEFAULT '',
                    resolved_at INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_dispute_escrow ON disputes(escrow_id);
                CREATE INDEX IF NOT EXISTS idx_dispute_status ON disputes(status);

                -- 履约记录表
                CREATE TABLE IF NOT EXISTS performance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE NOT NULL,
                    task_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    buyer_wallet TEXT NOT NULL,
                    seller_wallet TEXT NOT NULL,
                    seller_agent_id TEXT NOT NULL,
                    chain TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    status TEXT NOT NULL,
                    success INTEGER DEFAULT 0,
                    score REAL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER DEFAULT 0,
                    response_time_ms INTEGER DEFAULT 0,
                    payment_tx TEXT DEFAULT '',
                    payment_amount TEXT DEFAULT '0',
                    evidence TEXT DEFAULT '',
                    disputed INTEGER DEFAULT 0,
                    dispute_reason TEXT DEFAULT '',
                    resolution TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_perf_seller ON performance_records(seller_agent_id);
                CREATE INDEX IF NOT EXISTS idx_perf_buyer ON performance_records(buyer_wallet);
                CREATE INDEX IF NOT EXISTS idx_perf_status ON performance_records(status);
                CREATE INDEX IF NOT EXISTS idx_perf_created ON performance_records(created_at);

                -- 信用分快照表
                CREATE TABLE IF NOT EXISTS sacred_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    wallet TEXT NOT NULL,
                    total_score REAL NOT NULL,
                    grade TEXT NOT NULL,
                    stability_score REAL DEFAULT 0,
                    activity_score REAL DEFAULT 0,
                    creditworthiness_score REAL DEFAULT 0,
                    reliability_score REAL DEFAULT 0,
                    ecosystem_score REAL DEFAULT 0,
                    is_cold_start INTEGER DEFAULT 0,
                    snapshot_hash TEXT NOT NULL,
                    calculated_at INTEGER NOT NULL,
                    UNIQUE(agent_id, calculated_at)
                );

                CREATE INDEX IF NOT EXISTS idx_sacred_agent ON sacred_scores(agent_id);
                CREATE INDEX IF NOT EXISTS idx_sacred_score ON sacred_scores(total_score DESC);
                CREATE INDEX IF NOT EXISTS idx_sacred_grade ON sacred_scores(grade);

                -- 维度明细表
                CREATE TABLE IF NOT EXISTS dimension_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    calculated_at INTEGER NOT NULL,
                    dimension TEXT NOT NULL,
                    raw_score REAL DEFAULT 0,
                    weighted_score REAL DEFAULT 0,
                    components_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_dim_agent ON dimension_details(agent_id);

                -- 查询授权表
                CREATE TABLE IF NOT EXISTS query_authorizations (
                    auth_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    querier_id TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    revoked INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_auth_agent ON query_authorizations(agent_id);

                -- 严重违约表
                CREATE TABLE IF NOT EXISTS severe_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    wallet TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    violation_type TEXT NOT NULL,
                    penalty_points REAL NOT NULL,
                    occurred_at INTEGER NOT NULL,
                    decay_exempt INTEGER DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_violation_agent ON severe_violations(agent_id);
            """)
            conn.commit()
        finally:
            conn.close()

    # ═════════════════════════════════════════════════════
    # 托管操作
    # ═════════════════════════════════════════════════════

    def create_escrow(
        self,
        buyer: str,
        seller: str,
        amount: float,
        token: str = "BNB",
        timeout: int = 86400,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """创建托管"""
        escrow_id = f"escrow_{uuid.uuid4().hex[:12]}"
        now = int(time.time())

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO escrows
                   (escrow_id, buyer, seller, amount, token, timeout, status,
                    created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (escrow_id, buyer, seller, str(amount), token, timeout,
                 now, json.dumps(metadata or {})),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "escrow_id": escrow_id,
            "buyer": buyer,
            "seller": seller,
            "amount": amount,
            "token": token,
            "timeout": timeout,
            "status": "pending",
            "created_at": now,
            "metadata": metadata or {},
        }

    def get_escrow(self, escrow_id: str) -> Optional[Dict]:
        """获取托管"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM escrows WHERE escrow_id = ?",
                (escrow_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_escrow(row)
        finally:
            conn.close()

    def update_escrow_status(
        self,
        escrow_id: str,
        status: str,
        **kwargs,
    ) -> Optional[Dict]:
        """更新托管状态"""
        conn = self._connect()
        try:
            # 构建更新字段
            updates = ["status = ?"]
            values = [status]

            for key in ["fund_tx", "delivery_proof", "evidence", "resolution"]:
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    values.append(kwargs[key])

            # 时间戳字段
            for key in ["funded_at", "delivered_at", "completed_at"]:
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    values.append(kwargs[key])

            if "disputed" in kwargs:
                updates.append("disputed = ?")
                values.append(1 if kwargs["disputed"] else 0)

            if "dispute_reason" in kwargs:
                updates.append("dispute_reason = ?")
                values.append(kwargs["dispute_reason"])

            values.append(escrow_id)

            conn.execute(
                f"UPDATE escrows SET {', '.join(updates)} WHERE escrow_id = ?",
                values,
            )
            conn.commit()

            return self.get_escrow(escrow_id)
        finally:
            conn.close()

    def list_escrows_by_status(self, status: str) -> List[Dict]:
        """按状态列出托管"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM escrows WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            return [self._row_to_escrow(r) for r in rows]
        finally:
            conn.close()

    def list_escrows_by_buyer(self, buyer: str) -> List[Dict]:
        """按买家列出托管"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM escrows WHERE buyer = ? ORDER BY created_at DESC",
                (buyer,),
            ).fetchall()
            return [self._row_to_escrow(r) for r in rows]
        finally:
            conn.close()

    def list_escrows_by_seller(self, seller: str) -> List[Dict]:
        """按卖家列出托管"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM escrows WHERE seller = ? ORDER BY created_at DESC",
                (seller,),
            ).fetchall()
            return [self._row_to_escrow(r) for r in rows]
        finally:
            conn.close()

    def _row_to_escrow(self, row) -> Dict:
        """数据库行转托管字典"""
        return {
            "escrow_id": row["escrow_id"],
            "buyer": row["buyer"],
            "seller": row["seller"],
            "amount": row["amount"],
            "token": row["token"],
            "timeout": row["timeout"],
            "status": row["status"],
            "created_at": row["created_at"],
            "funded_at": row["funded_at"],
            "delivered_at": row["delivered_at"],
            "completed_at": row["completed_at"],
            "fund_tx": row["fund_tx"],
            "delivery_proof": row["delivery_proof"],
            "evidence": row["evidence"],
            "disputed": bool(row["disputed"]),
            "dispute_reason": row["dispute_reason"],
            "resolution": row["resolution"],
            "metadata": json.loads(row["metadata"]),
        }

    # ═════════════════════════════════════════════════════
    # 争议操作
    # ═════════════════════════════════════════════════════

    def create_dispute(
        self,
        escrow_id: str,
        reason: str,
        evidence: Optional[Dict] = None,
    ) -> Dict:
        """创建争议"""
        dispute_id = f"dispute_{uuid.uuid4().hex[:12]}"
        now = int(time.time())

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO disputes
                   (dispute_id, escrow_id, reason, evidence, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (dispute_id, escrow_id, reason, json.dumps(evidence or {}), now),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "dispute_id": dispute_id,
            "escrow_id": escrow_id,
            "reason": reason,
            "evidence": evidence or {},
            "status": "pending",
            "created_at": now,
            "arbitrators": [],
            "votes": [],
            "result": None,
        }

    def get_dispute(self, dispute_id: str) -> Optional[Dict]:
        """获取争议"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM disputes WHERE dispute_id = ?",
                (dispute_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_dispute(row)
        finally:
            conn.close()

    def add_dispute_evidence(self, dispute_id: str, evidence: Dict) -> Optional[Dict]:
        """添加证据"""
        conn = self._connect()
        try:
            dispute = self.get_dispute(dispute_id)
            if not dispute:
                return None

            evidence_list = dispute.get("evidence_list", [])
            evidence["added_at"] = int(time.time())
            evidence_list.append(evidence)

            conn.execute(
                "UPDATE disputes SET evidence_list = ? WHERE dispute_id = ?",
                (json.dumps(evidence_list), dispute_id),
            )
            conn.commit()

            return self.get_dispute(dispute_id)
        finally:
            conn.close()

    def assign_arbitrators(
        self,
        dispute_id: str,
        arbitrators: List[Dict],
    ) -> Optional[Dict]:
        """分配仲裁员"""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE disputes SET arbitrators = ?, status = 'arbitrating' "
                "WHERE dispute_id = ?",
                (json.dumps(arbitrators), dispute_id),
            )
            conn.commit()
            return self.get_dispute(dispute_id)
        finally:
            conn.close()

    def add_vote(
        self,
        dispute_id: str,
        arbitrator: str,
        vote: str,
        weight: float,
    ) -> Optional[Dict]:
        """添加投票"""
        conn = self._connect()
        try:
            dispute = self.get_dispute(dispute_id)
            if not dispute:
                return None

            votes = dispute.get("votes", [])
            votes.append({
                "arbitrator": arbitrator,
                "vote": vote,
                "weight": weight,
                "voted_at": int(time.time()),
            })

            conn.execute(
                "UPDATE disputes SET votes = ? WHERE dispute_id = ?",
                (json.dumps(votes), dispute_id),
            )
            conn.commit()

            return self.get_dispute(dispute_id)
        finally:
            conn.close()

    def resolve_dispute(
        self,
        dispute_id: str,
        result: str,
        reason: str = "",
    ) -> Optional[Dict]:
        """解决争议"""
        conn = self._connect()
        try:
            now = int(time.time())
            conn.execute(
                """UPDATE disputes
                   SET status = 'resolved', result = ?, resolution_reason = ?,
                       resolved_at = ?
                   WHERE dispute_id = ?""",
                (result, reason, now, dispute_id),
            )
            conn.commit()
            return self.get_dispute(dispute_id)
        finally:
            conn.close()

    def list_pending_disputes(self) -> List[Dict]:
        """列出待处理争议"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM disputes WHERE status = 'pending' "
                "ORDER BY created_at DESC",
            ).fetchall()
            return [self._row_to_dispute(r) for r in rows]
        finally:
            conn.close()

    def list_disputes_by_escrow(self, escrow_id: str) -> List[Dict]:
        """按托管ID列出争议"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM disputes WHERE escrow_id = ? ORDER BY created_at DESC",
                (escrow_id,),
            ).fetchall()
            return [self._row_to_dispute(r) for r in rows]
        finally:
            conn.close()

    def _row_to_dispute(self, row) -> Dict:
        """数据库行转争议字典"""
        return {
            "dispute_id": row["dispute_id"],
            "escrow_id": row["escrow_id"],
            "reason": row["reason"],
            "evidence": json.loads(row["evidence"]),
            "evidence_list": json.loads(row["evidence_list"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "arbitrators": json.loads(row["arbitrators"]),
            "votes": json.loads(row["votes"]),
            "result": row["result"],
            "resolution_reason": row["resolution_reason"],
            "resolved_at": row["resolved_at"],
        }

    # ═════════════════════════════════════════════════════
    # 履约记录操作
    # ═════════════════════════════════════════════════════

    def save_performance_record(self, record) -> None:
        """保存履约记录"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO performance_records
                   (record_id, task_id, task_type, buyer_wallet, seller_wallet,
                    seller_agent_id, chain, amount, status, success, score,
                    created_at, completed_at, response_time_ms, payment_tx,
                    payment_amount, evidence, disputed, dispute_reason, resolution)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id, record.task_id, record.task_type,
                    record.buyer_wallet, record.seller_wallet, record.seller_agent_id,
                    record.chain, record.amount, record.status.value,
                    1 if record.success else 0, record.score,
                    record.created_at, record.completed_at, record.response_time_ms,
                    record.payment_tx, record.payment_amount, record.evidence,
                    1 if record.disputed else 0, record.dispute_reason, record.resolution,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_performance_records(
        self,
        agent_id: str = None,
        wallet: str = None,
        limit: int = 1000,
    ) -> List:
        """获取履约记录"""
        conn = self._connect()
        try:
            if agent_id:
                rows = conn.execute(
                    "SELECT * FROM performance_records WHERE seller_agent_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (agent_id, limit),
                ).fetchall()
            elif wallet:
                rows = conn.execute(
                    "SELECT * FROM performance_records "
                    "WHERE seller_wallet = ? OR buyer_wallet = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (wallet, wallet, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM performance_records "
                    "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            return [self._row_to_performance_record(r) for r in rows]
        finally:
            conn.close()

    def _row_to_performance_record(self, row):
        """数据库行转 PerformanceRecord"""
        from credit.models import PerformanceRecord, TaskStatus
        return PerformanceRecord(
            record_id=row["record_id"],
            task_id=row["task_id"],
            task_type=row["task_type"],
            buyer_wallet=row["buyer_wallet"],
            seller_wallet=row["seller_wallet"],
            seller_agent_id=row["seller_agent_id"],
            chain=row["chain"],
            amount=row["amount"],
            status=TaskStatus.from_value(row["status"]),
            success=bool(row["success"]),
            score=row["score"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            response_time_ms=row["response_time_ms"],
            payment_tx=row["payment_tx"],
            payment_amount=row["payment_amount"],
            evidence=row["evidence"],
            disputed=bool(row["disputed"]),
            dispute_reason=row["dispute_reason"],
            resolution=row["resolution"],
        )

    def close(self):
        """关闭连接（SQLite 连接是每次调用创建的，无需关闭）"""
        pass
