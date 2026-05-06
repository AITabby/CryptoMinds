"""
信用分数据持久化 — 使用独立 SQLite 数据库

与现有 cryptominds.db 完全分离，互不干扰。
"""

import json
import sqlite3
import time
from typing import Dict, List, Optional

from .config import DEFAULT_DB_PATH
from .models import (SacredScore, DimensionScore, QueryAuthorization,
                     ScoreHistoryEntry, PerformanceRecord)


class CreditScoreStore:
    """信用分数据持久化"""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """创建表结构"""
        conn = self._connect()
        try:
            conn.executescript("""
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
                CREATE INDEX IF NOT EXISTS idx_sacred_calculated ON sacred_scores(calculated_at);

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
                CREATE INDEX IF NOT EXISTS idx_dim_calc ON dimension_details(calculated_at);

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
                CREATE INDEX IF NOT EXISTS idx_auth_querier ON query_authorizations(querier_id);

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
                CREATE INDEX IF NOT EXISTS idx_violation_wallet ON severe_violations(wallet);

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

                CREATE TABLE IF NOT EXISTS escrow_states (
                    escrow_id TEXT PRIMARY KEY NOT NULL,
                    buyer TEXT NOT NULL,
                    seller TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    token TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    funded_at INTEGER DEFAULT 0,
                    delivered_at INTEGER DEFAULT 0,
                    completed_at INTEGER DEFAULT 0,
                    fund_tx TEXT DEFAULT '',
                    evidence TEXT DEFAULT '',
                    disputed INTEGER DEFAULT 0,
                    disputed_at INTEGER DEFAULT 0,
                    dispute_reason TEXT DEFAULT '',
                    resolution TEXT DEFAULT '',
                    block_number INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_escrow_seller ON escrow_states(seller);
                CREATE INDEX IF NOT EXISTS idx_escrow_buyer ON escrow_states(buyer);
                CREATE INDEX IF NOT EXISTS idx_escrow_status ON escrow_states(status);
            """)
            conn.commit()
        finally:
            conn.close()

    # ── 信用分快照 ──────────────────────────────────

    def save_score(self, score: SacredScore) -> None:
        """保存计算结果快照"""
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
                    score.creditworthiness.weighted_score, score.reliability.weighted_score,
                    score.ecosystem.weighted_score,
                    1 if score.is_cold_start else 0, score.snapshot_hash, score.calculated_at,
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

    def get_latest_score(self, agent_id: str) -> Optional[SacredScore]:
        """获取最新一次计算结果"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM sacred_scores WHERE agent_id = ? "
                "ORDER BY calculated_at DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
            if not row:
                return None

            # 获取明细
            dims = conn.execute(
                "SELECT * FROM dimension_details WHERE agent_id = ? AND calculated_at = ?",
                (agent_id, row["calculated_at"]),
            ).fetchall()

            dim_map = {}
            for d in dims:
                dim_map[d["dimension"]] = DimensionScore(
                    dimension=d["dimension"],
                    name={"S": "Stability", "A": "Activity", "C": "Creditworthiness",
                          "R": "Reliability", "E": "Ecosystem"}.get(d["dimension"], ""),
                    raw_score=d["raw_score"],
                    weighted_score=d["weighted_score"],
                    components=json.loads(d["components_json"]),
                )

            score = SacredScore(
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
            return score
        finally:
            conn.close()

    def get_score_history(self, agent_id: str, limit: int = 30) -> List[ScoreHistoryEntry]:
        """获取历史分数变化"""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT s.*, GROUP_CONCAT(d.dimension || ':' || d.weighted_score) as dim_scores
                   FROM sacred_scores s
                   LEFT JOIN dimension_details d
                       ON s.agent_id = d.agent_id AND s.calculated_at = d.calculated_at
                   WHERE s.agent_id = ?
                   GROUP BY s.calculated_at
                   ORDER BY s.calculated_at DESC
                   LIMIT ?""",
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

                result.append(ScoreHistoryEntry(
                    agent_id=agent_id,
                    score=row["total_score"],
                    grade=row["grade"],
                    dimension_scores=dim_scores,
                    calculated_at=row["calculated_at"],
                ))

            return result
        finally:
            conn.close()

    def get_score_statistics(self) -> Dict:
        """获取所有 Agent 的分数统计，用于同行对比"""
        conn = self._connect()
        try:
            # 获取每个 Agent 最新分数
            rows = conn.execute("""
                SELECT s1.total_score, s1.grade
                FROM sacred_scores s1
                INNER JOIN (
                    SELECT agent_id, MAX(calculated_at) as max_cal
                    FROM sacred_scores GROUP BY agent_id
                ) s2 ON s1.agent_id = s2.agent_id AND s1.calculated_at = s2.max_cal
            """).fetchall()

            if not rows:
                return {"total_agents": 0, "avg_score": 0, "median_score": 0,
                        "percentiles": {}, "grade_counts": {}}

            scores = sorted([r["total_score"] for r in rows])
            grade_counts = {}
            for r in rows:
                grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

            n = len(scores)
            avg = sum(scores) / n
            median = scores[n // 2]

            percentiles = {
                "p10": scores[int(n * 0.1)],
                "p25": scores[int(n * 0.25)],
                "p50": median,
                "p75": scores[int(n * 0.75)],
                "p90": scores[int(n * 0.9)],
            }

            return {
                "total_agents": n,
                "avg_score": round(avg, 1),
                "median_score": round(median, 1),
                "percentiles": percentiles,
                "grade_counts": grade_counts,
            }
        finally:
            conn.close()

    # ── 查询授权 ────────────────────────────────────

    def save_authorization(self, auth: QueryAuthorization) -> None:
        """保存查询授权"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO query_authorizations
                   (auth_id, agent_id, querier_id, signature, expires_at, created_at, revoked)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (auth.auth_id, auth.agent_id, auth.querier_id,
                 auth.signature, auth.expires_at, auth.created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def verify_authorization(self, auth_id: str, querier_id: str) -> bool:
        """验证查询授权是否有效"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM query_authorizations "
                "WHERE auth_id = ? AND querier_id = ? AND revoked = 0",
                (auth_id, querier_id),
            ).fetchone()
            if not row:
                return False
            return row["expires_at"] > int(time.time())
        finally:
            conn.close()

    def list_authorizations(self, agent_id: str) -> List[QueryAuthorization]:
        """列出 Agent 发出的授权"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM query_authorizations "
                "WHERE agent_id = ? AND revoked = 0 ORDER BY created_at DESC",
                (agent_id,),
            ).fetchall()
            return [QueryAuthorization(
                auth_id=r["auth_id"],
                agent_id=r["agent_id"],
                querier_id=r["querier_id"],
                signature=r["signature"],
                expires_at=r["expires_at"],
                created_at=r["created_at"],
            ) for r in rows]
        finally:
            conn.close()

    def revoke_authorization(self, auth_id: str) -> bool:
        """撤销授权"""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE query_authorizations SET revoked = 1 WHERE auth_id = ?",
                (auth_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── 排行榜 ──────────────────────────────────────

    def get_leaderboard(self, limit: int = 50, grade: str = None) -> List[Dict]:
        """获取排行榜"""
        conn = self._connect()
        try:
            if grade:
                rows = conn.execute(
                    """SELECT s1.* FROM sacred_scores s1
                       INNER JOIN (
                           SELECT agent_id, MAX(calculated_at) as max_cal
                           FROM sacred_scores GROUP BY agent_id
                       ) s2 ON s1.agent_id = s2.agent_id AND s1.calculated_at = s2.max_cal
                       WHERE s1.grade = ?
                       ORDER BY s1.total_score DESC LIMIT ?""",
                    (grade, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT s1.* FROM sacred_scores s1
                       INNER JOIN (
                           SELECT agent_id, MAX(calculated_at) as max_cal
                           FROM sacred_scores GROUP BY agent_id
                       ) s2 ON s1.agent_id = s2.agent_id AND s1.calculated_at = s2.max_cal
                       ORDER BY s1.total_score DESC LIMIT ?""",
                    (limit,),
                ).fetchall()

            return [
                {
                    "rank": i + 1,
                    "agent_id": r["agent_id"],
                    "wallet": r["wallet"],
                    "total_score": r["total_score"],
                    "grade": r["grade"],
                    "is_cold_start": bool(r["is_cold_start"]),
                }
                for i, r in enumerate(rows)
            ]
        finally:
            conn.close()

    # ── 严重违约 ────────────────────────────────────

    def record_severe_violation(self, agent_id: str, wallet: str, record_id: str,
                                violation_type: str, penalty_points: float,
                                occurred_at: int) -> None:
        """记录严重违约"""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO severe_violations
                   (agent_id, wallet, record_id, violation_type,
                    penalty_points, occurred_at, decay_exempt)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (agent_id, wallet, record_id, violation_type,
                 penalty_points, occurred_at),
            )
            conn.commit()
        finally:
            conn.close()

    def get_severe_violations(self, agent_id: str) -> List[Dict]:
        """获取严重违约记录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM severe_violations WHERE agent_id = ?",
                (agent_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── 履约记录 ──────────────────────────────────────

    def save_performance_record(self, record: PerformanceRecord) -> None:
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
    ) -> List[PerformanceRecord]:
        """
        获取履约记录

        Args:
            agent_id: Agent ID（seller_agent_id）
            wallet: 钱包地址（seller_wallet 或 buyer_wallet）
            limit: 最大记录数
        """
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

    def _row_to_performance_record(self, row) -> PerformanceRecord:
        """数据库行转 PerformanceRecord"""
        from .models import TaskStatus
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

    # ── 托管状态 ──────────────────────────────────────

    def save_escrow_state(self, escrow: Dict) -> None:
        """
        保存托管状态

        Args:
            escrow: 托管状态字典
        """
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO escrow_states
                   (escrow_id, buyer, seller, amount, token, status,
                    created_at, funded_at, delivered_at, completed_at,
                    fund_tx, evidence, disputed, disputed_at,
                    dispute_reason, resolution, block_number)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    escrow["escrow_id"], escrow["buyer"], escrow["seller"],
                    escrow["amount"], escrow.get("token", ""), escrow["status"],
                    escrow["created_at"], escrow.get("funded_at", 0),
                    escrow.get("delivered_at", 0), escrow.get("completed_at", 0),
                    escrow.get("fund_tx", ""), escrow.get("evidence", ""),
                    1 if escrow.get("disputed") else 0,
                    escrow.get("disputed_at", 0), escrow.get("dispute_reason", ""),
                    escrow.get("resolution", ""), escrow.get("block_number", 0),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_escrow_state(self, escrow_id: str) -> Optional[Dict]:
        """
        获取托管状态

        Args:
            escrow_id: 托管 ID

        Returns:
            托管状态字典，不存在返回 None
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM escrow_states WHERE escrow_id = ?",
                (escrow_id,),
            ).fetchone()
            if not row:
                return None

            return {
                "escrow_id": row["escrow_id"],
                "buyer": row["buyer"],
                "seller": row["seller"],
                "amount": row["amount"],
                "token": row["token"],
                "status": row["status"],
                "created_at": row["created_at"],
                "funded_at": row["funded_at"],
                "delivered_at": row["delivered_at"],
                "completed_at": row["completed_at"],
                "fund_tx": row["fund_tx"],
                "evidence": row["evidence"],
                "disputed": bool(row["disputed"]),
                "disputed_at": row["disputed_at"],
                "dispute_reason": row["dispute_reason"],
                "resolution": row["resolution"],
                "block_number": row["block_number"],
            }
        finally:
            conn.close()

    def get_active_escrows(self, seller: str = None, buyer: str = None) -> List[Dict]:
        """
        获取进行中的托管

        Args:
            seller: 卖家地址
            buyer: 买家地址

        Returns:
            托管状态列表
        """
        conn = self._connect()
        try:
            # 进行中的状态
            active_statuses = ("pending", "funded", "delivered", "disputed")

            if seller:
                rows = conn.execute(
                    "SELECT * FROM escrow_states WHERE seller = ? AND status IN (?, ?, ?, ?)",
                    (seller, *active_statuses),
                ).fetchall()
            elif buyer:
                rows = conn.execute(
                    "SELECT * FROM escrow_states WHERE buyer = ? AND status IN (?, ?, ?, ?)",
                    (buyer, *active_statuses),
                ).fetchall()
            else:
                placeholders = ",".join("?" * len(active_statuses))
                rows = conn.execute(
                    f"SELECT * FROM escrow_states WHERE status IN ({placeholders})",
                    active_statuses,
                ).fetchall()

            result = []
            for row in rows:
                result.append({
                    "escrow_id": row["escrow_id"],
                    "buyer": row["buyer"],
                    "seller": row["seller"],
                    "amount": row["amount"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                })
            return result
        finally:
            conn.close()

    def close(self) -> None:
        pass  # SQLite connections are per-call, no persistent connection to close
