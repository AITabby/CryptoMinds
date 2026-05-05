"""
只读桥接 — 从现有系统 SQLite 读取数据

不调用任何现有 Python 类的写方法，不修改现有数据库。
"""

import sqlite3
import json
from typing import Dict, List, Optional, Tuple

from .config import DEFAULT_DB_PATH


class CreditScoreBridge:
    """只读桥接 — 从现有 cryptominds.db 读取数据供信用分计算使用"""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or DEFAULT_DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    # ── 履约记录 ────────────────────────────────────

    def get_records_by_seller(self, wallet: str) -> List[Dict]:
        """从 performance_records 表读取卖家的履约记录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM performance_records WHERE seller_wallet = ? ORDER BY created_at DESC",
                (wallet,),
            ).fetchall()
            return [self._row_to_record_dict(r) for r in rows]
        finally:
            conn.close()

    def get_records_by_buyer(self, wallet: str) -> List[Dict]:
        """从 performance_records 表读取买家的记录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM performance_records WHERE buyer_wallet = ? ORDER BY created_at DESC",
                (wallet,),
            ).fetchall()
            return [self._row_to_record_dict(r) for r in rows]
        finally:
            conn.close()

    # ── 信用货币 ────────────────────────────────────

    def get_credit_currencies(self) -> List[Dict]:
        """从 credit_currencies 表读取所有信用货币"""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM credit_currencies WHERE active = 1").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_credit_acceptance(self, agent_id: str) -> Dict:
        """读取某 Agent 发行的货币被多少其他 Agent 接受"""
        conn = self._connect()
        try:
            # 找到该 Agent 发行的货币
            currencies = conn.execute(
                "SELECT currency_id, accepted_by FROM credit_currencies WHERE issuer_agent_id = ? AND active = 1",
                (agent_id,),
            ).fetchall()

            total_accepted = 0
            for c in currencies:
                accepted_by = c["accepted_by"]
                if accepted_by:
                    try:
                        agents = json.loads(accepted_by) if isinstance(accepted_by, str) else accepted_by
                        total_accepted += len(agents) if isinstance(agents, list) else 0
                    except (json.JSONDecodeError, TypeError):
                        pass

            return {
                "issued_count": len(currencies),
                "accepted_count": total_accepted,
            }
        finally:
            conn.close()

    def get_accepted_by_agent(self, agent_id: str) -> int:
        """读取该 Agent 接受了多少种信用货币"""
        conn = self._connect()
        try:
            currencies = conn.execute(
                "SELECT currency_id, accepted_by FROM credit_currencies WHERE active = 1"
            ).fetchall()

            count = 0
            for c in currencies:
                accepted_by = c["accepted_by"]
                if accepted_by:
                    try:
                        agents = json.loads(accepted_by) if isinstance(accepted_by, str) else accepted_by
                        if isinstance(agents, list) and agent_id in agents:
                            count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass

            return count
        finally:
            conn.close()

    # ── 托管订单 ────────────────────────────────────

    def get_escrow_orders_by_seller(self, wallet: str) -> List[Dict]:
        """从 escrow_orders 表读取托管记录"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM escrow_orders WHERE seller_wallet = ? ORDER BY created_at DESC",
                (wallet,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Agent 信息 ──────────────────────────────────

    def get_agent_wallet(self, agent_id: str) -> Optional[str]:
        """获取 Agent 的钱包地址"""
        conn = self._connect()
        try:
            # 先尝试从 session_keys 获取
            row = conn.execute(
                "SELECT main_wallet FROM session_keys WHERE agent_id = ? LIMIT 1",
                (agent_id,),
            ).fetchone()
            if row:
                return row["main_wallet"]

            # 再从 performance_records 获取
            row = conn.execute(
                "SELECT seller_wallet FROM performance_records WHERE seller_agent_id = ? LIMIT 1",
                (agent_id,),
            ).fetchone()
            return row["seller_wallet"] if row else None
        finally:
            conn.close()

    def get_all_agent_wallets(self) -> List[Tuple[str, str]]:
        """获取所有 (agent_id, wallet) 对"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT seller_agent_id, seller_wallet FROM performance_records WHERE seller_agent_id != ''"
            ).fetchall()
            return [(r["seller_agent_id"], r["seller_wallet"]) for r in rows]
        finally:
            conn.close()

    # ── 统计查询 ────────────────────────────────────

    def get_unique_counterparts(self, wallet: str) -> int:
        """获取与该钱包交互的唯一对手方数量"""
        conn = self._connect()
        try:
            buyers = conn.execute(
                "SELECT COUNT(DISTINCT buyer_wallet) FROM performance_records WHERE seller_wallet = ?",
                (wallet,),
            ).fetchone()[0]
            sellers = conn.execute(
                "SELECT COUNT(DISTINCT seller_wallet) FROM performance_records WHERE buyer_wallet = ?",
                (wallet,),
            ).fetchone()[0]
            return buyers + sellers
        finally:
            conn.close()

    def get_chain_coverage(self, wallet: str) -> List[str]:
        """获取该钱包活跃的链列表"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT chain FROM performance_records WHERE seller_wallet = ? AND chain != ''",
                (wallet,),
            ).fetchall()
            return [r["chain"] for r in rows]
        finally:
            conn.close()

    # ── 内部方法 ────────────────────────────────────

    def _row_to_record_dict(self, row: sqlite3.Row) -> Dict:
        """将数据库行转为 PerformanceRecord 兼容的字典"""
        return {
            "record_id": row["record_id"],
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "buyer_wallet": row["buyer_wallet"],
            "seller_wallet": row["seller_wallet"],
            "seller_agent_id": row["seller_agent_id"],
            "chain": row["chain"],
            "amount": row["amount"],
            "status": row["status"],
            "success": bool(row["success"]),
            "score": row["score"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "response_time_ms": row["response_time_ms"],
            "payment_tx": row["payment_tx"],
            "payment_amount": row["payment_amount"],
            "evidence": row["evidence"],
            "disputed": bool(row["disputed"]),
            "dispute_reason": row["dispute_reason"],
            "resolution": row["resolution"],
        }

    def records_to_performance_records(self, record_dicts: List[Dict]) -> list:
        """将字典列表转换为 PerformanceRecord 对象列表"""
        from reputation.record import PerformanceRecord
        return [PerformanceRecord.from_dict(d) for d in record_dicts]
