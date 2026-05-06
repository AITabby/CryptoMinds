"""CryptoMinds SQLite data adapter — bridges Python and Node.js data layers."""
from __future__ import annotations

# flake8: noqa
import json
import sqlite3
import os
import shutil
import time
import threading
import atexit
from decimal import Decimal
from typing import Dict, List, Optional
from pathlib import Path


DB_BACKUP_INTERVAL = int(os.getenv("DB_BACKUP_INTERVAL_SECONDS", "3600"))  # 1 hour default
DB_BACKUP_DIR = os.getenv("DB_BACKUP_DIR", "")


def _connect(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite with WAL mode and busy_timeout for cross-process safety."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # wait up to 5s on lock contention
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def backup_db(db_path: str, backup_dir: str = None) -> str:
    """Create a timestamped backup of the SQLite database with WAL checkpoint.

    Returns the backup file path.
    """
    backup_dir = backup_dir or DB_BACKUP_DIR or str(Path(db_path).parent / "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cryptominds_{timestamp}.db")

    # WAL checkpoint before copy to ensure all data is in the main file
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    shutil.copy2(db_path, backup_path)

    # Rotate: keep last 10 backups
    backups = sorted(Path(backup_dir).glob("cryptominds_*.db"), reverse=True)
    for old in backups[10:]:
        old.unlink(missing_ok=True)

    return backup_path


def start_backup_thread(db_path: str, interval: int = None):
    """Start a background thread that periodically backs up the database."""
    interval = interval or DB_BACKUP_INTERVAL
    if interval <= 0:
        return  # disabled

    def _loop():
        while True:
            time.sleep(interval)
            try:
                path = backup_db(db_path)
                print(f"[backup] SQLite backup created: {path}")
            except Exception as e:
                print(f"[backup] Backup failed: {e}")

    t = threading.Thread(target=_loop, daemon=True, name="sqlite-backup")
    t.start()
    return t


def register_shutdown_checkpoint(db_path: str):
    """Register an atexit handler to WAL checkpoint on process shutdown."""
    def _checkpoint():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception:
            pass
    atexit.register(_checkpoint)


def _ensure_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist (extends Node.js schema)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS performance_records (
            record_id TEXT PRIMARY KEY,
            task_id TEXT,
            task_type TEXT,
            buyer_wallet TEXT,
            seller_wallet TEXT,
            seller_agent_id TEXT,
            chain TEXT,
            amount TEXT,
            status TEXT DEFAULT 'pending',
            success INTEGER DEFAULT 0,
            score REAL DEFAULT 0,
            created_at INTEGER,
            completed_at INTEGER,
            response_time_ms INTEGER DEFAULT 0,
            payment_tx TEXT,
            payment_amount TEXT,
            evidence TEXT,
            disputed INTEGER DEFAULT 0,
            dispute_reason TEXT DEFAULT '',
            resolution TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS credit_currencies (
            currency_id TEXT PRIMARY KEY,
            issuer_agent_id TEXT,
            issuer_wallet TEXT,
            name TEXT,
            symbol TEXT,
            max_supply TEXT,
            backed_by TEXT,
            active INTEGER DEFAULT 1,
            created_at INTEGER,
            accepted_by TEXT
        );

        CREATE TABLE IF NOT EXISTS credit_balances (
            currency_id TEXT,
            wallet TEXT,
            balance TEXT,
            PRIMARY KEY (currency_id, wallet)
        );

        CREATE INDEX IF NOT EXISTS idx_records_seller
            ON performance_records(seller_wallet);
        CREATE INDEX IF NOT EXISTS idx_records_buyer
            ON performance_records(buyer_wallet);
        CREATE INDEX IF NOT EXISTS idx_records_task
            ON performance_records(task_id);

        CREATE TABLE IF NOT EXISTS escrow_orders (
            escrow_id TEXT PRIMARY KEY,
            task_id TEXT,
            order_id TEXT,
            buyer_wallet TEXT NOT NULL,
            seller_wallet TEXT NOT NULL,
            seller_agent_id TEXT,
            amount TEXT NOT NULL,
            channel_id TEXT,
            chain TEXT DEFAULT 'bsc',
            on_chain_order_id TEXT,
            chain_synced INTEGER DEFAULT 1,
            state TEXT DEFAULT 'created',
            created_at INTEGER,
            funded_at INTEGER,
            delivered_at INTEGER,
            verified_at INTEGER,
            disputed_at INTEGER,
            resolved_at INTEGER,
            seller_timeout_at INTEGER,
            buyer_timeout_at INTEGER,
            dispute_reason TEXT DEFAULT '',
            dispute_initiator TEXT DEFAULT '',
            arbitration_weight_buyer REAL DEFAULT 0,
            arbitration_weight_seller REAL DEFAULT 0,
            resolution TEXT DEFAULT '',
            resolution_reason TEXT DEFAULT '',
            verification_score REAL DEFAULT 0,
            verification_threshold REAL DEFAULT 0.7,
            dispute_window_seconds INTEGER DEFAULT 172800,
            evidence TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_escrow_task ON escrow_orders(task_id);
        CREATE INDEX IF NOT EXISTS idx_escrow_seller ON escrow_orders(seller_wallet);
        CREATE INDEX IF NOT EXISTS idx_escrow_state ON escrow_orders(state);


        CREATE TABLE IF NOT EXISTS session_keys (
            session_key_id TEXT PRIMARY KEY,
            main_wallet TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            available_chains TEXT,
            per_tx_limit TEXT,
            total_quota TEXT,
            total_used TEXT DEFAULT '0',
            callable_actions TEXT,
            created_at INTEGER,
            expires_at INTEGER,
            nonce INTEGER DEFAULT 0,
            revoked INTEGER DEFAULT 0,
            revoked_at INTEGER DEFAULT 0,
            session_address TEXT NOT NULL,
            authorization_signature TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_session_agent ON session_keys(agent_id);
        CREATE INDEX IF NOT EXISTS idx_session_wallet ON session_keys(main_wallet);

        CREATE TABLE IF NOT EXISTS vouchers (
            voucher_id TEXT PRIMARY KEY,
            issuer_wallet TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            capability_task_type TEXT NOT NULL,
            unit_price TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            total_units INTEGER NOT NULL,
            units_used INTEGER DEFAULT 0,
            total_deposit TEXT NOT NULL,
            channel_id TEXT DEFAULT 'mock',
            chain TEXT DEFAULT 'mock',
            escrow_id TEXT,
            state TEXT DEFAULT 'issued',
            created_at INTEGER,
            activated_at INTEGER DEFAULT 0,
            exhausted_at INTEGER DEFAULT 0,
            cancelled_at INTEGER DEFAULT 0,
            disputed_at INTEGER DEFAULT 0,
            resolved_at INTEGER DEFAULT 0,
            expires_at INTEGER DEFAULT 0,
            dispute_reason TEXT DEFAULT '',
            dispute_initiator TEXT DEFAULT '',
            resolution TEXT DEFAULT '',
            resolution_reason TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_voucher_agent ON vouchers(agent_id);
        CREATE INDEX IF NOT EXISTS idx_voucher_issuer ON vouchers(issuer_wallet);
        CREATE INDEX IF NOT EXISTS idx_voucher_state ON vouchers(state);

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            action TEXT NOT NULL,
            agent_id TEXT DEFAULT '',
            wallet TEXT DEFAULT '',
            target_id TEXT DEFAULT '',
            details_json TEXT DEFAULT '{}',
            result TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
    """)
    conn.commit()


def _migrate(conn: sqlite3.Connection):
    """Add columns that may not exist in older databases."""
    # Check if disputed column exists in performance_records
    try:
        conn.execute("SELECT disputed FROM performance_records LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE performance_records ADD COLUMN disputed INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE performance_records ADD COLUMN dispute_reason TEXT DEFAULT ''")
        conn.execute("ALTER TABLE performance_records ADD COLUMN resolution TEXT DEFAULT ''")
        conn.commit()

    # Check if chain_synced column exists in escrow_orders
    try:
        conn.execute("SELECT chain_synced FROM escrow_orders LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE escrow_orders ADD COLUMN chain_synced INTEGER DEFAULT 1")
        conn.commit()


class SqliteRecordStore:
    """SQLite-backed performance record store, replacing in-memory RecordStore."""

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
        _migrate(self._conn)
        # In-memory cache for fast lookups
        self._records: Dict[str, object] = {}
        self._seller_index: Dict[str, List[str]] = {}
        self._buyer_index: Dict[str, List[str]] = {}
        self._load_all()

    def _load_all(self):
        """Load all records from SQLite into memory cache."""
        from reputation.record import PerformanceRecord
        rows = self._conn.execute("SELECT * FROM performance_records").fetchall()
        for row in rows:
            record = self._row_to_record(row)
            self._records[record.record_id] = record
            if record.seller_wallet:
                self._seller_index.setdefault(record.seller_wallet, []).append(record.record_id)
            if record.buyer_wallet:
                self._buyer_index.setdefault(record.buyer_wallet, []).append(record.record_id)

    def _row_to_record(self, row) -> object:
        from reputation.record import PerformanceRecord, TaskStatus
        status_val = row["status"] or "pending"
        try:
            status = TaskStatus(status_val)
        except ValueError:
            status = TaskStatus.PENDING

        evidence = row["evidence"]
        if evidence:
            try:
                evidence = json.loads(evidence)
            except (json.JSONDecodeError, TypeError):
                evidence = {}

        return PerformanceRecord(
            record_id=row["record_id"],
            task_id=row["task_id"] or "",
            task_type=row["task_type"] or "",
            buyer_wallet=row["buyer_wallet"] or "",
            seller_wallet=row["seller_wallet"] or "",
            seller_agent_id=row["seller_agent_id"] or "",
            chain=row["chain"] or "bsc",
            amount=Decimal(row["amount"] or "0"),
            status=status,
            success=bool(row["success"]),
            score=float(row["score"] or 0),
            created_at=row["created_at"] or 0,
            completed_at=row["completed_at"] or 0,
            response_time_ms=int(row["response_time_ms"] or 0),
            payment_tx=row["payment_tx"] or "",
            payment_amount=Decimal(row["payment_amount"] or "0"),
            evidence=evidence,
            disputed=bool(row["disputed"] if "disputed" in row.keys() else 0),
            dispute_reason=row["dispute_reason"] if "dispute_reason" in row.keys() else "",
            resolution=row["resolution"] if "resolution" in row.keys() else "",
        )

    def _record_to_row(self, record) -> dict:
        return {
            "record_id": record.record_id,
            "task_id": record.task_id,
            "task_type": record.task_type,
            "buyer_wallet": record.buyer_wallet,
            "seller_wallet": record.seller_wallet,
            "seller_agent_id": record.seller_agent_id,
            "chain": record.chain,
            "amount": str(record.amount),
            "status": record.status.value if hasattr(record.status, 'value') else str(record.status),
            "success": int(record.success),
            "score": record.score,
            "created_at": record.created_at,
            "completed_at": record.completed_at,
            "response_time_ms": record.response_time_ms,
            "payment_tx": record.payment_tx,
            "payment_amount": str(record.payment_amount),
            "evidence": json.dumps(record.evidence, ensure_ascii=False) if record.evidence else "",
            "disputed": int(record.disputed),
            "dispute_reason": record.dispute_reason or "",
            "resolution": record.resolution or "",
        }

    def save(self, record) -> None:
        """Save a performance record to SQLite and cache."""
        self._records[record.record_id] = record
        if record.seller_wallet:
            self._seller_index.setdefault(record.seller_wallet, []).append(record.record_id)
        if record.buyer_wallet:
            self._buyer_index.setdefault(record.buyer_wallet, []).append(record.record_id)

        row = self._record_to_row(record)
        cols = ", ".join(row.keys())
        vals = ", ".join(["?"] * len(row))
        updates = ", ".join([f"{k}=?" for k in row.keys() if k != "record_id"])
        self._conn.execute(
            f"INSERT INTO performance_records ({cols}) VALUES ({vals}) ON CONFLICT(record_id) DO UPDATE SET {updates}",
            list(row.values()) + [v for k, v in row.items() if k != "record_id"],
        )
        self._conn.commit()

    def get(self, record_id: str) -> Optional[object]:
        return self._records.get(record_id)

    def get_by_task(self, task_id: str) -> Optional[object]:
        for record in self._records.values():
            if record.task_id == task_id:
                return record
        return None

    def get_by_seller(self, seller_wallet: str, limit: int = 100) -> List[object]:
        ids = self._seller_index.get(seller_wallet, [])[:limit]
        return [self._records[id] for id in ids if id in self._records]

    def get_by_buyer(self, buyer_wallet: str, limit: int = 100) -> List[object]:
        ids = self._buyer_index.get(buyer_wallet, [])[:limit]
        return [self._records[id] for id in ids if id in self._records]

    def count(self) -> int:
        return len(self._records)


class SqliteCreditStore:
    """SQLite-backed credit registry, replacing JSON-based CreditRegistry."""

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
        _migrate(self._conn)
        # In-memory state
        self._currencies: Dict[str, object] = {}
        self._balances: Dict[str, Dict[str, Decimal]] = {}
        self._issuer_index: Dict[str, str] = {}
        self._load_all()

    def _load_all(self):
        from reputation.credit import CreditCurrency
        rows = self._conn.execute("SELECT * FROM credit_currencies").fetchall()
        for row in rows:
            currency = CreditCurrency(
                currency_id=row["currency_id"],
                issuer_agent_id=row["issuer_agent_id"] or "",
                issuer_wallet=row["issuer_wallet"] or "",
                name=row["name"] or "",
                symbol=row["symbol"] or "",
                max_supply=Decimal(row["max_supply"] or "0"),
                backed_by=row["backed_by"] or "",
                active=bool(row["active"]),
                created_at=row["created_at"] or 0,
                accepted_by=json.loads(row["accepted_by"] or "[]"),
            )
            self._currencies[currency.currency_id] = currency
            if currency.issuer_wallet:
                self._issuer_index[currency.issuer_wallet] = currency.currency_id

        # Load balances
        bal_rows = self._conn.execute("SELECT * FROM credit_balances").fetchall()
        for row in bal_rows:
            cid = row["currency_id"]
            wallet = row["wallet"]
            balance = Decimal(row["balance"] or "0")
            self._balances.setdefault(cid, {})[wallet] = balance

    def _save_currency(self, currency):
        accepted_by_json = json.dumps(currency.accepted_by, ensure_ascii=False)
        self._conn.execute(
            """INSERT INTO credit_currencies
               (currency_id, issuer_agent_id, issuer_wallet, name, symbol, max_supply, backed_by, active, created_at, accepted_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(currency_id) DO UPDATE SET
               active=?, accepted_by=?""",
            (currency.currency_id, currency.issuer_agent_id, currency.issuer_wallet,
             currency.name, currency.symbol, str(currency.max_supply), currency.backed_by,
             int(currency.active), currency.created_at, accepted_by_json,
             int(currency.active), accepted_by_json),
        )
        self._conn.commit()

    def _save_balance(self, currency_id: str, wallet: str, balance: Decimal):
        self._conn.execute(
            """INSERT INTO credit_balances (currency_id, wallet, balance)
               VALUES (?, ?, ?)
               ON CONFLICT(currency_id, wallet) DO UPDATE SET balance=?""",
            (currency_id, wallet, str(balance), str(balance)),
        )
        self._conn.commit()

    # ── Interface matching CreditRegistry ──────────────

    def issue(self, issuer_agent_id: str, issuer_wallet: str, name: str, symbol: str,
              max_supply: Decimal, backed_by: str = "", min_reputation_score: float = 4.0) -> Dict:
        """Issue a new credit currency (matches CreditRegistry.issue signature)."""
        from reputation.credit import CreditCurrency
        import hashlib, time

        if issuer_wallet in self._issuer_index:
            return {"error": "该钱包已发行信用货币"}

        currency_id = hashlib.sha256(
            f"{issuer_wallet}{symbol}{time.time()}".encode()
        ).hexdigest()[:16]

        currency = CreditCurrency(
            currency_id=currency_id,
            issuer_agent_id=issuer_agent_id,
            issuer_wallet=issuer_wallet,
            name=name,
            symbol=symbol,
            max_supply=max_supply,
            backed_by=backed_by,
            min_reputation_score=min_reputation_score,
        )

        self._currencies[currency_id] = currency
        self._issuer_index[issuer_wallet] = currency_id
        self._balances[currency_id] = {issuer_wallet: max_supply}
        self._save_currency(currency)
        self._save_balance(currency_id, issuer_wallet, max_supply)

        return {
            "ok": True,
            "currency_id": currency_id,
            "message": f"信用货币 {symbol} 发行成功",
        }

    def list_all(self) -> List[Dict]:
        """列出所有货币 (matches CreditRegistry.list_all)."""
        return [c.to_dict() for c in self._currencies.values()]

    def accept_currency(self, currency_id: str, agent_id: str) -> Dict:
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"ok": False, "error": "信用货币不存在"}
        if agent_id not in currency.accepted_by:
            currency.accepted_by.append(agent_id)
            self._save_currency(currency)
        return {"ok": True}

    def get_balance(self, currency_id: str, wallet: str) -> Decimal:
        return self._balances.get(currency_id, {}).get(wallet, Decimal("0"))

    def transfer(self, currency_id: str, from_wallet: str, to_wallet: str, amount: Decimal) -> Dict:
        from_bal = self.get_balance(currency_id, from_wallet)
        if from_bal < amount:
            return {"ok": False, "error": "余额不足"}

        self._balances.setdefault(currency_id, {})[from_wallet] = from_bal - amount
        self._balances.setdefault(currency_id, {})[to_wallet] = self.get_balance(currency_id, to_wallet) + amount

        self._save_balance(currency_id, from_wallet, from_bal - amount)
        self._save_balance(currency_id, to_wallet, self.get_balance(currency_id, to_wallet) + amount)

        return {"ok": True, "from_balance": str(from_bal - amount), "to_balance": str(self.get_balance(currency_id, to_wallet))}

    def get_by_issuer(self, wallet: str) -> Optional[object]:
        cid = self._issuer_index.get(wallet)
        if cid:
            return self._currencies.get(cid)
        return None

    def pay_with_credit(self, currency_id: str, from_wallet: str, to_wallet: str,
                        amount: Decimal, to_agent_id: str = None) -> Dict:
        """Pay with credit currency (matches CreditRegistry.pay_with_credit)."""
        import hashlib, time

        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}
        if not currency.active:
            return {"error": "货币已停用"}
        if to_agent_id and to_agent_id not in currency.accepted_by:
            return {"error": f"Agent {to_agent_id} 不接受此货币"}

        from_balance = self.get_balance(currency_id, from_wallet)
        if from_balance < amount:
            return {"error": f"余额不足: {from_balance} < {amount}"}

        self._balances.setdefault(currency_id, {})[from_wallet] = from_balance - amount
        to_new = self.get_balance(currency_id, to_wallet) + amount
        self._balances.setdefault(currency_id, {})[to_wallet] = to_new

        self._save_balance(currency_id, from_wallet, from_balance - amount)
        self._save_balance(currency_id, to_wallet, to_new)

        tx_hash = hashlib.sha256(
            f"{currency_id}{from_wallet}{to_wallet}{amount}{time.time()}".encode()
        ).hexdigest()[:32]

        return {
            "ok": True,
            "tx_hash": tx_hash,
            "currency_id": currency_id,
            "symbol": currency.symbol,
            "from_balance": str(from_balance - amount),
            "to_balance": str(to_new),
            "amount": str(amount),
        }

    def check_acceptance(self, currency_id: str, agent_id: str) -> Dict:
        """Check if an agent accepts a currency (matches CreditRegistry.check_acceptance)."""
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}

        accepted = agent_id in currency.accepted_by
        trust_score = self._get_trust_score(currency_id)

        return {
            "currency_id": currency_id,
            "symbol": currency.symbol,
            "issuer_agent_id": currency.issuer_agent_id,
            "accepted": accepted,
            "trust_score": trust_score,
            "min_reputation_score": currency.min_reputation_score,
        }

    def get_acceptable_currencies(self, agent_id: str, min_trust_score: float = 0.5) -> List[Dict]:
        """Get currencies acceptable by an agent (matches CreditRegistry.get_acceptable_currencies)."""
        result = []
        for currency in self._currencies.values():
            if not currency.active:
                continue
            trust_score = self._get_trust_score(currency.currency_id)
            if trust_score >= min_trust_score:
                accepted = agent_id in currency.accepted_by
                result.append({
                    "currency_id": currency.currency_id,
                    "symbol": currency.symbol,
                    "name": currency.name,
                    "issuer_agent_id": currency.issuer_agent_id,
                    "trust_score": trust_score,
                    "accepted": accepted,
                })
        return result

    def _get_trust_score(self, currency_id: str) -> float:
        """Calculate trust score based on issuer reputation and acceptance."""
        currency = self._currencies.get(currency_id)
        if not currency:
            return 0.0
        acceptance_rate = len(currency.accepted_by) / max(1, 5)
        return min(1.0, acceptance_rate * 0.7 + 0.3)


class SqliteAgentBridge:
    """Bridge Python AgentRegistry writes to the shared SQLite agents table.

    This ensures agents registered via the Python API appear in the Node.js dashboard.
    The Python AgentRegistry still uses its in-memory dict for fast lookups,
    but every register/unregister also writes to SQLite.
    """

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
        _migrate(self._conn)

    def save_agent(self, agent) -> None:
        """Write an agent to the SQLite agents table."""
        capabilities_json = json.dumps(
            [c.to_dict() for c in agent.capabilities], ensure_ascii=False
        ) if hasattr(agent, 'capabilities') and agent.capabilities else "[]"

        self._conn.execute(
            """INSERT INTO agents (id, wallet, name, framework, skills, active, fee_rate, deposit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wallet) DO UPDATE SET
               name=?, skills=?, active=?, fee_rate=?, deposit=?""",
            (agent.agent_id, agent.wallet, agent.name or "",
             "", capabilities_json, int(agent.online),
             str(agent.get_price("token_delivery", Decimal("0.01"))) if hasattr(agent, 'get_price') else "0",
             str(agent.staked) if hasattr(agent, 'staked') else "0",
             int(agent.created_at) if hasattr(agent, 'created_at') else 0,
             agent.name or "", capabilities_json, int(agent.online),
             str(agent.get_price("token_delivery", Decimal("0.01"))) if hasattr(agent, 'get_price') else "0",
             str(agent.staked) if hasattr(agent, 'staked') else "0"),
        )
        self._conn.commit()

    def remove_agent(self, agent_id: str, wallet: str) -> None:
        """Remove an agent from SQLite."""
        self._conn.execute("DELETE FROM agents WHERE id = ? OR wallet = ?", (agent_id, wallet))
        self._conn.commit()


class SqliteEscrowStore:
    """SQLite-backed escrow order store."""

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
        _migrate(self._conn)
        self._orders: Dict[str, EscrowOrder] = {}
        self._load_all()

    def _load_all(self):
        from escrow.models import EscrowOrder
        from settlement.escrow_state import EscrowState
        rows = self._conn.execute("SELECT * FROM escrow_orders").fetchall()
        for row in rows:
            order = self._row_to_order(row)
            self._orders[order.escrow_id] = order

    def _row_to_order(self, row) -> object:
        from escrow.models import EscrowOrder
        from settlement.escrow_state import EscrowState
        evidence = row["evidence"] or ""
        if evidence:
            try:
                evidence = json.loads(evidence)
            except (json.JSONDecodeError, TypeError):
                evidence = {}

        return EscrowOrder(
            escrow_id=row["escrow_id"],
            task_id=row["task_id"] or "",
            order_id=row["order_id"] or "",
            buyer_wallet=row["buyer_wallet"] or "",
            seller_wallet=row["seller_wallet"] or "",
            seller_agent_id=row["seller_agent_id"] or "",
            amount=Decimal(row["amount"] or "0"),
            channel_id=row["channel_id"] or "",
            chain=row["chain"] or "bsc",
            on_chain_order_id=row["on_chain_order_id"] or None,
            chain_synced=bool(row["chain_synced"] if "chain_synced" in row.keys() else 1),
            state=EscrowState(row["state"] or "created"),
            created_at=row["created_at"] or 0,
            funded_at=row["funded_at"] or 0,
            delivered_at=row["delivered_at"] or 0,
            verified_at=row["verified_at"] or 0,
            disputed_at=row["disputed_at"] or 0,
            resolved_at=row["resolved_at"] or 0,
            seller_timeout_at=row["seller_timeout_at"] or 0,
            buyer_timeout_at=row["buyer_timeout_at"] or 0,
            dispute_reason=row["dispute_reason"] or "",
            dispute_initiator=row["dispute_initiator"] or "",
            arbitration_weight_buyer=float(row["arbitration_weight_buyer"] or 0),
            arbitration_weight_seller=float(row["arbitration_weight_seller"] or 0),
            resolution=row["resolution"] or "",
            resolution_reason=row["resolution_reason"] or "",
            verification_score=float(row["verification_score"] or 0),
            verification_threshold=float(row["verification_threshold"] or 0.7),
            dispute_window_seconds=int(row["dispute_window_seconds"] or 172800),
            verification_evidence=evidence,
        )

    def _order_to_row(self, order) -> dict:
        return {
            "escrow_id": order.escrow_id,
            "task_id": order.task_id,
            "order_id": order.order_id,
            "buyer_wallet": order.buyer_wallet,
            "seller_wallet": order.seller_wallet,
            "seller_agent_id": order.seller_agent_id,
            "amount": str(order.amount),
            "channel_id": order.channel_id,
            "chain": order.chain,
            "on_chain_order_id": order.on_chain_order_id or "",
            "chain_synced": int(order.chain_synced),
            "state": order.state.value,
            "created_at": order.created_at,
            "funded_at": order.funded_at,
            "delivered_at": order.delivered_at,
            "verified_at": order.verified_at,
            "disputed_at": order.disputed_at,
            "resolved_at": order.resolved_at,
            "seller_timeout_at": order.seller_timeout_at,
            "buyer_timeout_at": order.buyer_timeout_at,
            "dispute_reason": order.dispute_reason,
            "dispute_initiator": order.dispute_initiator,
            "arbitration_weight_buyer": order.arbitration_weight_buyer,
            "arbitration_weight_seller": order.arbitration_weight_seller,
            "resolution": order.resolution,
            "resolution_reason": order.resolution_reason,
            "verification_score": order.verification_score,
            "verification_threshold": order.verification_threshold,
            "dispute_window_seconds": order.dispute_window_seconds,
            "evidence": json.dumps(order.verification_evidence, ensure_ascii=False) if order.verification_evidence else "",
        }

    def save(self, order) -> None:
        self._orders[order.escrow_id] = order
        row = self._order_to_row(order)
        cols = ", ".join(row.keys())
        vals = ", ".join(["?"] * len(row))
        updates = ", ".join([f"{k}=?" for k in row.keys() if k != "escrow_id"])
        self._conn.execute(
            f"INSERT INTO escrow_orders ({cols}) VALUES ({vals}) ON CONFLICT(escrow_id) DO UPDATE SET {updates}",
            list(row.values()) + [v for k, v in row.items() if k != "escrow_id"],
        )
        self._conn.commit()

    def get(self, escrow_id: str) -> Optional[object]:
        return self._orders.get(escrow_id)

    def get_by_task(self, task_id: str) -> Optional[object]:
        for order in self._orders.values():
            if order.task_id == task_id:
                return order
        return None

    def get_by_state(self, state) -> List[object]:
        return [o for o in self._orders.values() if o.state == state]

    def get_by_seller(self, seller_wallet: str) -> List[object]:
        return [o for o in self._orders.values() if o.seller_wallet == seller_wallet]

    def count(self) -> int:
        return len(self._orders)


class SqliteSessionKeyStore:
    """SQLite-backed session key store."""

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
        _migrate(self._conn)
        self._keys: Dict[str, object] = {}
        self._load_all()

    def _load_all(self):
        from auth.session_key import SessionKey
        rows = self._conn.execute("SELECT * FROM session_keys").fetchall()
        for row in rows:
            key = self._row_to_key(row)
            self._keys[key.session_key_id] = key

    def _row_to_key(self, row) -> object:
        from auth.session_key import SessionKey
        chains = row["available_chains"] or "[]"
        try:
            chains = json.loads(chains)
        except (json.JSONDecodeError, TypeError):
            chains = []
        actions = row["callable_actions"] or "[]"
        try:
            actions = json.loads(actions)
        except (json.JSONDecodeError, TypeError):
            actions = []

        return SessionKey(
            session_key_id=row["session_key_id"],
            main_wallet=row["main_wallet"] or "",
            agent_id=row["agent_id"] or "",
            available_chains=chains,
            per_tx_limit=Decimal(row["per_tx_limit"] or "0"),
            total_quota=Decimal(row["total_quota"] or "0"),
            total_used=Decimal(row["total_used"] or "0"),
            callable_actions=actions,
            created_at=row["created_at"] or 0,
            expires_at=row["expires_at"] or 0,
            nonce=row["nonce"] or 0,
            revoked=bool(row["revoked"] or 0),
            revoked_at=row["revoked_at"] or 0,
            session_address=row["session_address"] or "",
            authorization_signature=row["authorization_signature"] or "",
        )

    def _key_to_row(self, key) -> dict:
        return {
            "session_key_id": key.session_key_id,
            "main_wallet": key.main_wallet,
            "agent_id": key.agent_id,
            "available_chains": json.dumps(key.available_chains),
            "per_tx_limit": str(key.per_tx_limit),
            "total_quota": str(key.total_quota),
            "total_used": str(key.total_used),
            "callable_actions": json.dumps(key.callable_actions),
            "created_at": key.created_at,
            "expires_at": key.expires_at,
            "nonce": key.nonce,
            "revoked": int(key.revoked),
            "revoked_at": key.revoked_at,
            "session_address": key.session_address,
            "authorization_signature": key.authorization_signature,
        }

    def save(self, key) -> None:
        self._keys[key.session_key_id] = key
        row = self._key_to_row(key)
        cols = ", ".join(row.keys())
        vals = ", ".join(["?"] * len(row))
        updates = ", ".join([f"{k}=?" for k in row.keys() if k != "session_key_id"])
        self._conn.execute(
            f"INSERT INTO session_keys ({cols}) VALUES ({vals}) ON CONFLICT(session_key_id) DO UPDATE SET {updates}",
            list(row.values()) + [v for k, v in row.items() if k != "session_key_id"],
        )
        self._conn.commit()

    def get(self, session_key_id: str) -> Optional[object]:
        return self._keys.get(session_key_id)

    def get_by_agent(self, agent_id: str) -> List[object]:
        return [k for k in self._keys.values() if k.agent_id == agent_id and not k.revoked]

    def revoke(self, session_key_id: str) -> bool:
        key = self._keys.get(session_key_id)
        if not key:
            return False
        key.nonce += 1
        key.revoked = True
        key.revoked_at = int(time.time()) if 'time' in dir() else 0
        self.save(key)
        return True

    def increase_quota(self, session_key_id: str, additional: Decimal) -> bool:
        key = self._keys.get(session_key_id)
        if not key:
            return False
        key.total_quota += additional
        self.save(key)
        return True

    def update_usage(self, session_key_id: str, amount: Decimal) -> None:
        key = self._keys.get(session_key_id)
        if not key:
            return
        key.total_used += amount
        self.save(key)

    def count(self) -> int:
        return len(self._keys)


class SqliteVoucherStore:
    """SQLite-backed voucher store."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        _ensure_tables(self._conn)
        self._vouchers: Dict[str, Voucher] = {}
        self._load_all()

    def _load_all(self):
        from voucher.state import VoucherState
        rows = self._conn.execute("SELECT * FROM vouchers").fetchall()
        for row in rows:
            v = self._row_to_voucher(row, VoucherState)
            self._vouchers[v.voucher_id] = v

    def _row_to_voucher(self, row, VoucherState) -> Voucher:
        from voucher.models import Voucher
        return Voucher(
            voucher_id=row[0],
            issuer_wallet=row[1],
            agent_id=row[2],
            capability_task_type=row[3],
            unit_price=Decimal(str(row[4])),
            unit_type=row[5],
            total_units=row[6],
            units_used=row[7],
            total_deposit=Decimal(str(row[8])),
            channel_id=row[9],
            chain=row[10],
            escrow_id=row[11],
            state=VoucherState(row[12]),
            created_at=row[13],
            activated_at=row[14],
            exhausted_at=row[15],
            cancelled_at=row[16],
            disputed_at=row[17],
            resolved_at=row[18],
            expires_at=row[19],
            dispute_reason=row[20],
            dispute_initiator=row[21],
            resolution=row[22],
            resolution_reason=row[23],
        )

    def save(self, voucher: Voucher) -> None:
        self._vouchers[voucher.voucher_id] = voucher
        self._conn.execute("""
            INSERT OR REPLACE INTO vouchers VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            voucher.voucher_id, voucher.issuer_wallet, voucher.agent_id,
            voucher.capability_task_type, str(voucher.unit_price), voucher.unit_type,
            voucher.total_units, voucher.units_used, str(voucher.total_deposit),
            voucher.channel_id, voucher.chain, voucher.escrow_id,
            voucher.state.value, voucher.created_at, voucher.activated_at,
            voucher.exhausted_at, voucher.cancelled_at, voucher.disputed_at,
            voucher.resolved_at, voucher.expires_at, voucher.dispute_reason,
            voucher.dispute_initiator, voucher.resolution, voucher.resolution_reason,
        ))
        self._conn.commit()

    def get(self, voucher_id: str) -> Optional[Voucher]:
        return self._vouchers.get(voucher_id)

    def get_by_agent(self, agent_id: str) -> List[Voucher]:
        return [v for v in self._vouchers.values() if v.agent_id == agent_id]

    def get_by_issuer(self, issuer_wallet: str) -> List[Voucher]:
        return [v for v in self._vouchers.values() if v.issuer_wallet == issuer_wallet]

    def get_by_state(self, state) -> List[Voucher]:
        return [v for v in self._vouchers.values() if v.state == state]

    def count(self) -> int:
        return len(self._vouchers)
