"""CryptoMinds SQLite data adapter — bridges Python and Node.js data layers."""
import json
import sqlite3
import os
from decimal import Decimal
from typing import Dict, List, Optional
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite with WAL mode for concurrent read/write safety."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


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
            evidence TEXT
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
    """)
    conn.commit()


class SqliteRecordStore:
    """SQLite-backed performance record store, replacing in-memory RecordStore."""

    def __init__(self, db_path: str):
        self._conn = _connect(db_path)
        _ensure_tables(self._conn)
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