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

                -- Voucher 按量计费表
                CREATE TABLE IF NOT EXISTS vouchers (
                    voucher_id TEXT PRIMARY KEY NOT NULL,
                    issuer TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    total_units INTEGER NOT NULL,
                    units_used INTEGER DEFAULT 0,
                    unit_price REAL NOT NULL,
                    total_deposit REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'issued',
                    escrow_id TEXT DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_voucher_agent ON vouchers(agent_id);
                CREATE INDEX IF NOT EXISTS idx_voucher_issuer ON vouchers(issuer);
                CREATE INDEX IF NOT EXISTS idx_voucher_status ON vouchers(status);
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

    # ═════════════════════════════════════════════════════
    # 信用分操作
    # ═════════════════════════════════════════════════════

    def save_score(self, score) -> None:
        """保存信用分快照"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO sacred_scores
                   (agent_id, wallet, total_score, grade,
                    stability_score, activity_score, creditworthiness_score,
                    reliability_score, ecosystem_score,
                    is_cold_start, snapshot_hash, calculated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    score.agent_id, score.wallet, score.total_score, score.grade,
                    score.stability.weighted_score, score.activity.weighted_score,
                    score.creditworthiness.weighted_score,
                    score.reliability.weighted_score, score.ecosystem.weighted_score,
                    1 if score.is_cold_start else 0,
                    score.snapshot_hash, score.calculated_at,
                ),
            )

            # 保存五维明细
            for dim_code, dim in score.dimensions.items():
                conn.execute(
                    """INSERT INTO dimension_details
                       (agent_id, calculated_at, dimension, raw_score,
                        weighted_score, components_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        score.agent_id, score.calculated_at, dim_code,
                        dim.raw_score, dim.weighted_score,
                        json.dumps(dim.components),
                    ),
                )

            conn.commit()
        finally:
            conn.close()

    def get_latest_score(self, agent_id: str):
        """获取最新一次信用分"""
        from credit.models import SacredScore, DimensionScore

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM sacred_scores WHERE agent_id = ? "
                "ORDER BY calculated_at DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
            if not row:
                return None

            # 获取维度明细
            dims = conn.execute(
                "SELECT * FROM dimension_details "
                "WHERE agent_id = ? AND calculated_at = ?",
                (agent_id, row["calculated_at"]),
            ).fetchall()

            dim_map = {}
            dim_names = {
                "S": "Stability", "A": "Activity",
                "C": "Creditworthiness", "R": "Reliability",
                "E": "Ecosystem",
            }
            for d in dims:
                dim_map[d["dimension"]] = DimensionScore(
                    dimension=d["dimension"],
                    name=dim_names.get(d["dimension"], ""),
                    raw_score=d["raw_score"],
                    weighted_score=d["weighted_score"],
                    components=json.loads(d["components_json"]),
                )

            return SacredScore(
                agent_id=row["agent_id"],
                wallet=row["wallet"],
                stability=dim_map.get("S", DimensionScore("S", "Stability")),
                activity=dim_map.get("A", DimensionScore("A", "Activity")),
                creditworthiness=dim_map.get("C", DimensionScore("C", "Creditworthiness")),
                reliability=dim_map.get("R", DimensionScore("R", "Reliability")),
                ecosystem=dim_map.get("E", DimensionScore("E", "Ecosystem")),
                total_score=row["total_score"],
                grade=row["grade"],
                is_cold_start=bool(row["is_cold_start"]),
                calculated_at=row["calculated_at"],
                snapshot_hash=row["snapshot_hash"],
            )
        finally:
            conn.close()

    def get_score_history(self, agent_id: str, limit: int = 30) -> List[Dict]:
        """获取信用分历史"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT s.*, GROUP_CONCAT(d.dimension || ':' || d.weighted_score) as dim_scores "
                "FROM sacred_scores s "
                "LEFT JOIN dimension_details d "
                "    ON s.agent_id = d.agent_id AND s.calculated_at = d.calculated_at "
                "WHERE s.agent_id = ? "
                "GROUP BY s.calculated_at "
                "ORDER BY s.calculated_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()

            result = []
            for row in rows:
                dim_scores = {}
                if row["dim_scores"]:
                    for pair in row["dim_scores"].split(","):
                        parts = pair.split(":")
                        if len(parts) == 2:
                            dim_scores[parts[0]] = float(parts[1])

                result.append({
                    "agent_id": agent_id,
                    "score": row["total_score"],
                    "grade": row["grade"],
                    "dimension_scores": dim_scores,
                    "calculated_at": row["calculated_at"],
                })
            return result
        finally:
            conn.close()

    def get_leaderboard(self, limit: int = 50, grade: str = None) -> List[Dict]:
        """获取信用分排行榜"""
        conn = self._connect()
        try:
            # 统一用子查询：每个 agent 取最新一条
            if grade:
                rows = conn.execute(
                    "SELECT s1.agent_id, s1.wallet, s1.total_score, s1.grade, s1.calculated_at "
                    "FROM sacred_scores s1 "
                    "INNER JOIN ("
                    "    SELECT agent_id, MAX(calculated_at) as max_cal "
                    "    FROM sacred_scores GROUP BY agent_id"
                    ") s2 ON s1.agent_id = s2.agent_id AND s1.calculated_at = s2.max_cal "
                    "WHERE s1.grade = ? "
                    "ORDER BY s1.total_score DESC LIMIT ?",
                    (grade, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT s1.agent_id, s1.wallet, s1.total_score, s1.grade, s1.calculated_at "
                    "FROM sacred_scores s1 "
                    "INNER JOIN ("
                    "    SELECT agent_id, MAX(calculated_at) as max_cal "
                    "    FROM sacred_scores GROUP BY agent_id"
                    ") s2 ON s1.agent_id = s2.agent_id AND s1.calculated_at = s2.max_cal "
                    "ORDER BY s1.total_score DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            result = []
            for i, row in enumerate(rows, 1):
                result.append({
                    "rank": i,
                    "agent_id": row["agent_id"],
                    "wallet": row["wallet"],
                    "total_score": row["total_score"],
                    "grade": row["grade"],
                    "calculated_at": row["calculated_at"],
                })
            return result
        finally:
            conn.close()

    # ═════════════════════════════════════════════════════
    # 查询授权操作
    # ═════════════════════════════════════════════════════

    def save_authorization(self, auth) -> None:
        """保存查询授权"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO query_authorizations
                   (auth_id, agent_id, querier_id, signature, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (auth.auth_id, auth.agent_id, auth.querier_id,
                 auth.signature, auth.expires_at, auth.created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def verify_authorization(self, auth_id: str, querier_id: str) -> bool:
        """验证查询授权"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM query_authorizations WHERE auth_id = ? AND revoked = 0",
                (auth_id,),
            ).fetchone()
            if not row:
                return False
            if row["querier_id"] != querier_id:
                return False
            if row["expires_at"] < int(time.time()):
                return False
            return True
        finally:
            conn.close()

    def list_authorizations(self, agent_id: str) -> List[Dict]:
        """列出授权"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM query_authorizations WHERE agent_id = ? AND revoked = 0 "
                "ORDER BY created_at DESC",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def revoke_authorization(self, auth_id: str) -> bool:
        """撤销授权"""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE query_authorizations SET revoked = 1 WHERE auth_id = ?",
                (auth_id,),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    # ═════════════════════════════════════════════════════
    # 严重违约操作
    # ═════════════════════════════════════════════════════

    def record_severe_violation(
        self,
        agent_id: str,
        wallet: str,
        record_id: str,
        violation_type: str,
        penalty_points: float,
    ) -> None:
        """记录严重违约"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO severe_violations
                   (agent_id, wallet, record_id, violation_type,
                    penalty_points, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (agent_id, wallet, record_id, violation_type,
                 penalty_points, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()

    def get_severe_violations(self, agent_id: str) -> List[Dict]:
        """获取严重违约记录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM severe_violations WHERE agent_id = ? "
                "ORDER BY occurred_at DESC",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ═════════════════════════════════════════════════════
    # 托管状态（链上同步用，支持 upsert）
    # ═════════════════════════════════════════════════════

    def upsert_escrow(self, escrow: Dict) -> Dict:
        """插入或更新托管状态（链上同步用）"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO escrows
                   (escrow_id, buyer, seller, amount, token, timeout, status,
                    created_at, funded_at, delivered_at, completed_at,
                    fund_tx, delivery_proof, evidence, disputed,
                    dispute_reason, resolution, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    escrow["escrow_id"], escrow.get("buyer", ""),
                    escrow.get("seller", ""), escrow.get("amount", "0"),
                    escrow.get("token", "BNB"), escrow.get("timeout", 86400),
                    escrow.get("status", "pending"),
                    escrow.get("created_at", int(time.time())),
                    escrow.get("funded_at", 0), escrow.get("delivered_at", 0),
                    escrow.get("completed_at", 0), escrow.get("fund_tx", ""),
                    escrow.get("delivery_proof", ""), escrow.get("evidence", ""),
                    1 if escrow.get("disputed") else 0,
                    escrow.get("dispute_reason", ""),
                    escrow.get("resolution", ""),
                    json.dumps(escrow.get("metadata", {})),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_escrow(escrow["escrow_id"])

    def close(self):
        """关闭连接（SQLite 连接是每次调用创建的，无需关闭）"""
        pass

    # ═════════════════════════════════════════════════════
    # Voucher 操作
    # ═════════════════════════════════════════════════════

    def create_voucher(
        self,
        voucher_id: str,
        issuer: str,
        agent_id: str,
        total_units: int,
        unit_price: float,
        escrow_id: str = "",
    ) -> Dict:
        """创建 Voucher"""
        now = int(time.time())
        total_deposit = total_units * unit_price

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO vouchers
                   (voucher_id, issuer, agent_id, total_units, units_used,
                    unit_price, total_deposit, status, escrow_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?, 'issued', ?, ?, ?)""",
                (voucher_id, issuer, agent_id, total_units, unit_price,
                 total_deposit, escrow_id, now, now),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_voucher(voucher_id)

    def get_voucher(self, voucher_id: str) -> Optional[Dict]:
        """获取 Voucher"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM vouchers WHERE voucher_id = ?",
                (voucher_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def use_voucher(self, voucher_id: str, units: int) -> Optional[Dict]:
        """使用 Voucher 单位"""
        voucher = self.get_voucher(voucher_id)
        if not voucher:
            return None

        if voucher["status"] != "issued":
            return {"error": "Voucher 状态不允许使用"}

        new_used = voucher["units_used"] + units
        if new_used > voucher["total_units"]:
            return {"error": "超出可用额度"}

        new_status = "exhausted" if new_used >= voucher["total_units"] else "issued"
        now = int(time.time())

        conn = self._connect()
        try:
            conn.execute(
                """UPDATE vouchers
                   SET units_used = ?, status = ?, updated_at = ?
                   WHERE voucher_id = ?""",
                (new_used, new_status, now, voucher_id),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_voucher(voucher_id)

    def list_vouchers(self, agent_id: str = None, issuer: str = None) -> List[Dict]:
        """列出 Voucher"""
        conn = self._connect()
        try:
            if agent_id:
                rows = conn.execute(
                    "SELECT * FROM vouchers WHERE agent_id = ? ORDER BY created_at DESC",
                    (agent_id,),
                ).fetchall()
            elif issuer:
                rows = conn.execute(
                    "SELECT * FROM vouchers WHERE issuer = ? ORDER BY created_at DESC",
                    (issuer,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM vouchers ORDER BY created_at DESC",
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_voucher_status(self, voucher_id: str, status: str) -> Optional[Dict]:
        """更新 Voucher 状态"""
        now = int(time.time())
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE vouchers SET status = ?, updated_at = ? WHERE voucher_id = ?",
                (status, now, voucher_id),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_voucher(voucher_id)
