"""CryptoMinds PostgreSQL data adapter — production-grade concurrent storage."""

import json
import os
import time
import hashlib
from decimal import Decimal
from typing import Dict, List, Optional

import psycopg2
from psycopg2 import pool


DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Connection pool ────────────────────────────────────────

_pool: Optional[pool.SimpleConnectionPool] = None


def _get_pool(url: str = None) -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        url = url or DATABASE_URL
        _pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=int(os.getenv("PG_POOL_SIZE", "10")),
            dsn=url,
        )
    return _pool


def _get_conn(url: str = None):
    return _get_pool(url).getconn()


def _return_conn(conn):
    _get_pool().putconn(conn)


def _ensure_tables(conn):
    """Create tables if they don't exist (mirrors SQLite schema)."""
    cur = conn.cursor()
    cur.execute("""
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
            score DOUBLE PRECISION DEFAULT 0,
            created_at INTEGER,
            completed_at INTEGER,
            response_time_ms INTEGER DEFAULT 0,
            payment_tx TEXT,
            payment_amount TEXT,
            evidence JSONB DEFAULT '{}',
            disputed INTEGER DEFAULT 0,
            dispute_reason TEXT DEFAULT '',
            resolution TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_records_seller ON performance_records(seller_wallet);
        CREATE INDEX IF NOT EXISTS idx_records_buyer ON performance_records(buyer_wallet);
        CREATE INDEX IF NOT EXISTS idx_records_task ON performance_records(task_id);

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
            accepted_by JSONB DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS credit_balances (
            currency_id TEXT,
            wallet TEXT,
            balance TEXT,
            PRIMARY KEY (currency_id, wallet)
        );

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
            arbitration_weight_buyer DOUBLE PRECISION DEFAULT 0,
            arbitration_weight_seller DOUBLE PRECISION DEFAULT 0,
            resolution TEXT DEFAULT '',
            resolution_reason TEXT DEFAULT '',
            verification_score DOUBLE PRECISION DEFAULT 0,
            verification_threshold DOUBLE PRECISION DEFAULT 0.7,
            dispute_window_seconds INTEGER DEFAULT 172800,
            evidence JSONB DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_escrow_task ON escrow_orders(task_id);
        CREATE INDEX IF NOT EXISTS idx_escrow_seller ON escrow_orders(seller_wallet);
        CREATE INDEX IF NOT EXISTS idx_escrow_state ON escrow_orders(state);

        CREATE TABLE IF NOT EXISTS session_keys (
            session_key_id TEXT PRIMARY KEY,
            main_wallet TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            available_chains JSONB DEFAULT '[]',
            per_tx_limit TEXT,
            total_quota TEXT,
            total_used TEXT DEFAULT '0',
            callable_actions JSONB DEFAULT '[]',
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
            id SERIAL PRIMARY KEY,
            timestamp BIGINT NOT NULL,
            action TEXT NOT NULL,
            agent_id TEXT DEFAULT '',
            wallet TEXT DEFAULT '',
            target_id TEXT DEFAULT '',
            details_json JSONB DEFAULT '{}',
            result TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
    """)
    conn.commit()
    cur.close()


# ── Record Store ────────────────────────────────────────────

class PgRecordStore:
    """PostgreSQL-backed performance record store."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)
        self._records: Dict[str, object] = {}
        self._seller_index: Dict[str, List[str]] = {}
        self._buyer_index: Dict[str, List[str]] = {}
        self._load_all()

    def _load_all(self):
        from reputation.record import PerformanceRecord
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("SELECT * FROM performance_records")
        for row in cur.fetchall():
            record = self._row_to_record(row, cur.description)
            self._records[record.record_id] = record
            if record.seller_wallet:
                self._seller_index.setdefault(record.seller_wallet, []).append(record.record_id)
            if record.buyer_wallet:
                self._buyer_index.setdefault(record.buyer_wallet, []).append(record.record_id)
        cur.close()
        _return_conn(conn)

    def _row_to_record(self, row, description) -> object:
        from reputation.record import PerformanceRecord, TaskStatus
        col_names = [d[0] for d in description]
        row_dict = dict(zip(col_names, row))

        status_val = row_dict.get("status") or "pending"
        try:
            status = TaskStatus(status_val)
        except ValueError:
            status = TaskStatus.PENDING

        evidence = row_dict.get("evidence")
        if evidence:
            if isinstance(evidence, str):
                try:
                    evidence = json.loads(evidence)
                except (json.JSONDecodeError, TypeError):
                    evidence = {}
        else:
            evidence = {}

        return PerformanceRecord(
            record_id=row_dict.get("record_id", ""),
            task_id=row_dict.get("task_id", ""),
            task_type=row_dict.get("task_type", ""),
            buyer_wallet=row_dict.get("buyer_wallet", ""),
            seller_wallet=row_dict.get("seller_wallet", ""),
            seller_agent_id=row_dict.get("seller_agent_id", ""),
            chain=row_dict.get("chain", "bsc"),
            amount=Decimal(row_dict.get("amount") or "0"),
            status=status,
            success=bool(row_dict.get("success", 0)),
            score=float(row_dict.get("score") or 0),
            created_at=row_dict.get("created_at") or 0,
            completed_at=row_dict.get("completed_at") or 0,
            response_time_ms=int(row_dict.get("response_time_ms") or 0),
            payment_tx=row_dict.get("payment_tx", ""),
            payment_amount=Decimal(row_dict.get("payment_amount") or "0"),
            evidence=evidence,
            disputed=bool(row_dict.get("disputed", 0)),
            dispute_reason=row_dict.get("dispute_reason", ""),
            resolution=row_dict.get("resolution", ""),
        )

    def save(self, record) -> None:
        self._records[record.record_id] = record
        if record.seller_wallet:
            self._seller_index.setdefault(record.seller_wallet, []).append(record.record_id)
        if record.buyer_wallet:
            self._buyer_index.setdefault(record.buyer_wallet, []).append(record.record_id)

        conn = _get_conn(self._url)
        cur = conn.cursor()
        evidence_json = json.dumps(record.evidence, ensure_ascii=False) if record.evidence else "{}"
        cur.execute("""
            INSERT INTO performance_records (
                record_id, task_id, task_type, buyer_wallet, seller_wallet, seller_agent_id,
                chain, amount, status, success, score, created_at, completed_at,
                response_time_ms, payment_tx, payment_amount, evidence,
                disputed, dispute_reason, resolution
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(record_id) DO UPDATE SET
                task_id=%s, task_type=%s, buyer_wallet=%s, seller_wallet=%s,
                seller_agent_id=%s, chain=%s, amount=%s, status=%s, success=%s,
                score=%s, created_at=%s, completed_at=%s, response_time_ms=%s,
                payment_tx=%s, payment_amount=%s, evidence=%s,
                disputed=%s, dispute_reason=%s, resolution=%s
        """, (
            record.record_id, record.task_id, record.task_type,
            record.buyer_wallet, record.seller_wallet, record.seller_agent_id,
            record.chain, str(record.amount),
            record.status.value if hasattr(record.status, 'value') else str(record.status),
            int(record.success), record.score, record.created_at, record.completed_at,
            record.response_time_ms, record.payment_tx, str(record.payment_amount),
            evidence_json, int(record.disputed), record.dispute_reason or "", record.resolution or "",
            # update values (same order as SET clause)
            record.task_id, record.task_type, record.buyer_wallet, record.seller_wallet,
            record.seller_agent_id, record.chain, str(record.amount),
            record.status.value if hasattr(record.status, 'value') else str(record.status),
            int(record.success), record.score, record.created_at, record.completed_at,
            record.response_time_ms, record.payment_tx, str(record.payment_amount),
            evidence_json, int(record.disputed), record.dispute_reason or "", record.resolution or "",
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

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


# ── Credit Store ────────────────────────────────────────────

class PgCreditStore:
    """PostgreSQL-backed credit registry."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)
        self._currencies: Dict[str, object] = {}
        self._balances: Dict[str, Dict[str, Decimal]] = {}
        self._issuer_index: Dict[str, str] = {}
        self._load_all()

    def _load_all(self):
        from reputation.credit import CreditCurrency
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("SELECT * FROM credit_currencies")
        for row in cur.fetchall():
            col_names = [d[0] for d in cur.description]
            row_dict = dict(zip(col_names, row))
            accepted_by = row_dict.get("accepted_by", [])
            if isinstance(accepted_by, str):
                try:
                    accepted_by = json.loads(accepted_by)
                except (json.JSONDecodeError, TypeError):
                    accepted_by = []
            currency = CreditCurrency(
                currency_id=row_dict.get("currency_id", ""),
                issuer_agent_id=row_dict.get("issuer_agent_id", ""),
                issuer_wallet=row_dict.get("issuer_wallet", ""),
                name=row_dict.get("name", ""),
                symbol=row_dict.get("symbol", ""),
                max_supply=Decimal(row_dict.get("max_supply") or "0"),
                backed_by=row_dict.get("backed_by", ""),
                active=bool(row_dict.get("active", 1)),
                created_at=row_dict.get("created_at") or 0,
                accepted_by=accepted_by,
            )
            self._currencies[currency.currency_id] = currency
            if currency.issuer_wallet:
                self._issuer_index[currency.issuer_wallet] = currency.currency_id

        cur.execute("SELECT * FROM credit_balances")
        for row in cur.fetchall():
            col_names = [d[0] for d in cur.description]
            row_dict = dict(zip(col_names, row))
            cid = row_dict.get("currency_id", "")
            wallet = row_dict.get("wallet", "")
            balance = Decimal(row_dict.get("balance") or "0")
            self._balances.setdefault(cid, {})[wallet] = balance
        cur.close()
        _return_conn(conn)

    def _save_currency(self, currency):
        accepted_by_json = json.dumps(currency.accepted_by, ensure_ascii=False)
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO credit_currencies
                (currency_id, issuer_agent_id, issuer_wallet, name, symbol, max_supply, backed_by, active, created_at, accepted_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(currency_id) DO UPDATE SET
                active=%s, accepted_by=%s
        """, (
            currency.currency_id, currency.issuer_agent_id, currency.issuer_wallet,
            currency.name, currency.symbol, str(currency.max_supply), currency.backed_by,
            int(currency.active), currency.created_at, accepted_by_json,
            int(currency.active), accepted_by_json,
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

    def _save_balance(self, currency_id: str, wallet: str, balance: Decimal):
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO credit_balances (currency_id, wallet, balance)
                VALUES (%s, %s, %s)
            ON CONFLICT(currency_id, wallet) DO UPDATE SET balance=%s
        """, (currency_id, wallet, str(balance), str(balance)))
        conn.commit()
        cur.close()
        _return_conn(conn)

    def issue(self, issuer_agent_id: str, issuer_wallet: str, name: str, symbol: str,
              max_supply: Decimal, backed_by: str = "", min_reputation_score: float = 4.0) -> Dict:
        from reputation.credit import CreditCurrency
        if issuer_wallet in self._issuer_index:
            return {"error": "该钱包已发行信用货币"}
        currency_id = hashlib.sha256(
            f"{issuer_wallet}{symbol}{time.time()}".encode()
        ).hexdigest()[:16]
        currency = CreditCurrency(
            currency_id=currency_id, issuer_agent_id=issuer_agent_id,
            issuer_wallet=issuer_wallet, name=name, symbol=symbol,
            max_supply=max_supply, backed_by=backed_by,
            min_reputation_score=min_reputation_score,
        )
        self._currencies[currency_id] = currency
        self._issuer_index[issuer_wallet] = currency_id
        self._balances[currency_id] = {issuer_wallet: max_supply}
        self._save_currency(currency)
        self._save_balance(currency_id, issuer_wallet, max_supply)
        return {"ok": True, "currency_id": currency_id, "message": f"信用货币 {symbol} 发行成功"}

    def list_all(self) -> List[Dict]:
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
        return {"ok": True, "tx_hash": tx_hash, "currency_id": currency_id,
                "symbol": currency.symbol, "from_balance": str(from_balance - amount),
                "to_balance": str(to_new), "amount": str(amount)}

    def check_acceptance(self, currency_id: str, agent_id: str) -> Dict:
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}
        accepted = agent_id in currency.accepted_by
        trust_score = self._get_trust_score(currency_id)
        return {"currency_id": currency_id, "symbol": currency.symbol,
                "issuer_agent_id": currency.issuer_agent_id, "accepted": accepted,
                "trust_score": trust_score, "min_reputation_score": currency.min_reputation_score}

    def get_acceptable_currencies(self, agent_id: str, min_trust_score: float = 0.5) -> List[Dict]:
        result = []
        for currency in self._currencies.values():
            if not currency.active:
                continue
            trust_score = self._get_trust_score(currency.currency_id)
            if trust_score >= min_trust_score:
                accepted = agent_id in currency.accepted_by
                result.append({
                    "currency_id": currency.currency_id, "symbol": currency.symbol,
                    "name": currency.name, "issuer_agent_id": currency.issuer_agent_id,
                    "trust_score": trust_score, "accepted": accepted,
                })
        return result

    def _get_trust_score(self, currency_id: str) -> float:
        currency = self._currencies.get(currency_id)
        if not currency:
            return 0.0
        acceptance_rate = len(currency.accepted_by) / max(1, 5)
        return min(1.0, acceptance_rate * 0.7 + 0.3)


# ── Agent Bridge ────────────────────────────────────────────

class PgAgentBridge:
    """PostgreSQL-backed agent bridge."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)

    def save_agent(self, agent) -> None:
        capabilities_json = json.dumps(
            [c.to_dict() for c in agent.capabilities], ensure_ascii=False
        ) if hasattr(agent, 'capabilities') and agent.capabilities else "[]"
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agents (id, wallet, name, framework, skills, active, fee_rate, deposit, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(wallet) DO UPDATE SET
                name=%s, skills=%s, active=%s, fee_rate=%s, deposit=%s
        """, (
            agent.agent_id, agent.wallet, agent.name or "",
            "", capabilities_json, int(agent.online),
            str(agent.get_price("token_delivery", Decimal("0.01"))) if hasattr(agent, 'get_price') else "0",
            str(agent.staked) if hasattr(agent, 'staked') else "0",
            int(agent.created_at) if hasattr(agent, 'created_at') else 0,
            agent.name or "", capabilities_json, int(agent.online),
            str(agent.get_price("token_delivery", Decimal("0.01"))) if hasattr(agent, 'get_price') else "0",
            str(agent.staked) if hasattr(agent, 'staked') else "0",
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

    def remove_agent(self, agent_id: str, wallet: str) -> None:
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("DELETE FROM agents WHERE id = %s OR wallet = %s", (agent_id, wallet))
        conn.commit()
        cur.close()
        _return_conn(conn)


# ── Escrow Store ────────────────────────────────────────────

class PgEscrowStore:
    """PostgreSQL-backed escrow order store."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)
        self._orders: Dict[str, object] = {}
        self._load_all()

    def _load_all(self):
        from escrow.models import EscrowOrder
        from settlement.escrow_state import EscrowState
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("SELECT * FROM escrow_orders")
        for row in cur.fetchall():
            order = self._row_to_order(row, cur.description)
            self._orders[order.escrow_id] = order
        cur.close()
        _return_conn(conn)

    def _row_to_order(self, row, description) -> object:
        from escrow.models import EscrowOrder
        from settlement.escrow_state import EscrowState
        col_names = [d[0] for d in description]
        row_dict = dict(zip(col_names, row))

        evidence = row_dict.get("evidence")
        if evidence:
            if isinstance(evidence, str):
                try:
                    evidence = json.loads(evidence)
                except (json.JSONDecodeError, TypeError):
                    evidence = {}
        else:
            evidence = {}

        return EscrowOrder(
            escrow_id=row_dict.get("escrow_id", ""),
            task_id=row_dict.get("task_id", ""),
            order_id=row_dict.get("order_id", ""),
            buyer_wallet=row_dict.get("buyer_wallet", ""),
            seller_wallet=row_dict.get("seller_wallet", ""),
            seller_agent_id=row_dict.get("seller_agent_id", ""),
            amount=Decimal(row_dict.get("amount") or "0"),
            channel_id=row_dict.get("channel_id", ""),
            chain=row_dict.get("chain", "bsc"),
            on_chain_order_id=row_dict.get("on_chain_order_id") or None,
            state=EscrowState(row_dict.get("state") or "created"),
            created_at=row_dict.get("created_at") or 0,
            funded_at=row_dict.get("funded_at") or 0,
            delivered_at=row_dict.get("delivered_at") or 0,
            verified_at=row_dict.get("verified_at") or 0,
            disputed_at=row_dict.get("disputed_at") or 0,
            resolved_at=row_dict.get("resolved_at") or 0,
            seller_timeout_at=row_dict.get("seller_timeout_at") or 0,
            buyer_timeout_at=row_dict.get("buyer_timeout_at") or 0,
            dispute_reason=row_dict.get("dispute_reason", ""),
            dispute_initiator=row_dict.get("dispute_initiator", ""),
            arbitration_weight_buyer=float(row_dict.get("arbitration_weight_buyer") or 0),
            arbitration_weight_seller=float(row_dict.get("arbitration_weight_seller") or 0),
            resolution=row_dict.get("resolution", ""),
            resolution_reason=row_dict.get("resolution_reason", ""),
            verification_score=float(row_dict.get("verification_score") or 0),
            verification_threshold=float(row_dict.get("verification_threshold") or 0.7),
            dispute_window_seconds=int(row_dict.get("dispute_window_seconds") or 172800),
            verification_evidence=evidence,
        )

    def save(self, order) -> None:
        self._orders[order.escrow_id] = order
        evidence_json = json.dumps(order.verification_evidence, ensure_ascii=False) if order.verification_evidence else "{}"

        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO escrow_orders (
                escrow_id, task_id, order_id, buyer_wallet, seller_wallet, seller_agent_id,
                amount, channel_id, chain, on_chain_order_id, state,
                created_at, funded_at, delivered_at, verified_at, disputed_at, resolved_at,
                seller_timeout_at, buyer_timeout_at,
                dispute_reason, dispute_initiator,
                arbitration_weight_buyer, arbitration_weight_seller,
                resolution, resolution_reason,
                verification_score, verification_threshold, dispute_window_seconds, evidence
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            ) ON CONFLICT(escrow_id) DO UPDATE SET
                task_id=%s, order_id=%s, buyer_wallet=%s, seller_wallet=%s, seller_agent_id=%s,
                amount=%s, channel_id=%s, chain=%s, on_chain_order_id=%s, state=%s,
                funded_at=%s, delivered_at=%s, verified_at=%s, disputed_at=%s, resolved_at=%s,
                seller_timeout_at=%s, buyer_timeout_at=%s,
                dispute_reason=%s, dispute_initiator=%s,
                arbitration_weight_buyer=%s, arbitration_weight_seller=%s,
                resolution=%s, resolution_reason=%s,
                verification_score=%s, verification_threshold=%s, dispute_window_seconds=%s, evidence=%s
        """, (
            order.escrow_id, order.task_id, order.order_id, order.buyer_wallet,
            order.seller_wallet, order.seller_agent_id, str(order.amount),
            order.channel_id, order.chain, order.on_chain_order_id or "",
            order.state.value, order.created_at, order.funded_at, order.delivered_at,
            order.verified_at, order.disputed_at, order.resolved_at,
            order.seller_timeout_at, order.buyer_timeout_at,
            order.dispute_reason, order.dispute_initiator,
            order.arbitration_weight_buyer, order.arbitration_weight_seller,
            order.resolution, order.resolution_reason,
            order.verification_score, order.verification_threshold,
            order.dispute_window_seconds, evidence_json,
            # update values
            order.task_id, order.order_id, order.buyer_wallet, order.seller_wallet,
            order.seller_agent_id, str(order.amount), order.channel_id, order.chain,
            order.on_chain_order_id or "", order.state.value,
            order.funded_at, order.delivered_at, order.verified_at,
            order.disputed_at, order.resolved_at,
            order.seller_timeout_at, order.buyer_timeout_at,
            order.dispute_reason, order.dispute_initiator,
            order.arbitration_weight_buyer, order.arbitration_weight_seller,
            order.resolution, order.resolution_reason,
            order.verification_score, order.verification_threshold,
            order.dispute_window_seconds, evidence_json,
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

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


# ── Session Key Store ────────────────────────────────────────

class PgSessionKeyStore:
    """PostgreSQL-backed session key store."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)
        self._keys: Dict[str, object] = {}
        self._load_all()

    def _load_all(self):
        from auth.session_key import SessionKey
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_keys")
        for row in cur.fetchall():
            key = self._row_to_key(row, cur.description)
            self._keys[key.session_key_id] = key
        cur.close()
        _return_conn(conn)

    def _row_to_key(self, row, description) -> object:
        from auth.session_key import SessionKey
        col_names = [d[0] for d in description]
        row_dict = dict(zip(col_names, row))

        chains = row_dict.get("available_chains", [])
        if isinstance(chains, str):
            try:
                chains = json.loads(chains)
            except (json.JSONDecodeError, TypeError):
                chains = []
        actions = row_dict.get("callable_actions", [])
        if isinstance(actions, str):
            try:
                actions = json.loads(actions)
            except (json.JSONDecodeError, TypeError):
                actions = []

        return SessionKey(
            session_key_id=row_dict.get("session_key_id", ""),
            main_wallet=row_dict.get("main_wallet", ""),
            agent_id=row_dict.get("agent_id", ""),
            available_chains=chains,
            per_tx_limit=Decimal(row_dict.get("per_tx_limit") or "0"),
            total_quota=Decimal(row_dict.get("total_quota") or "0"),
            total_used=Decimal(row_dict.get("total_used") or "0"),
            callable_actions=actions,
            created_at=row_dict.get("created_at") or 0,
            expires_at=row_dict.get("expires_at") or 0,
            nonce=row_dict.get("nonce") or 0,
            revoked=bool(row_dict.get("revoked") or 0),
            revoked_at=row_dict.get("revoked_at") or 0,
            session_address=row_dict.get("session_address", ""),
            authorization_signature=row_dict.get("authorization_signature", ""),
        )

    def save(self, key) -> None:
        self._keys[key.session_key_id] = key
        chains_json = json.dumps(key.available_chains)
        actions_json = json.dumps(key.callable_actions)

        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO session_keys (
                session_key_id, main_wallet, agent_id, available_chains,
                per_tx_limit, total_quota, total_used, callable_actions,
                created_at, expires_at, nonce, revoked, revoked_at,
                session_address, authorization_signature
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(session_key_id) DO UPDATE SET
                main_wallet=%s, agent_id=%s, available_chains=%s,
                per_tx_limit=%s, total_quota=%s, total_used=%s, callable_actions=%s,
                expires_at=%s, nonce=%s, revoked=%s, revoked_at=%s,
                session_address=%s, authorization_signature=%s
        """, (
            key.session_key_id, key.main_wallet, key.agent_id, chains_json,
            str(key.per_tx_limit), str(key.total_quota), str(key.total_used), actions_json,
            key.created_at, key.expires_at, key.nonce, int(key.revoked), key.revoked_at,
            key.session_address, key.authorization_signature,
            # update values
            key.main_wallet, key.agent_id, chains_json,
            str(key.per_tx_limit), str(key.total_quota), str(key.total_used), actions_json,
            key.expires_at, key.nonce, int(key.revoked), key.revoked_at,
            key.session_address, key.authorization_signature,
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

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
        key.revoked_at = int(time.time())
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


# ── Voucher Store ────────────────────────────────────────────

class PgVoucherStore:
    """PostgreSQL-backed voucher store."""

    def __init__(self, database_url: str):
        self._url = database_url
        conn = _get_conn(database_url)
        _ensure_tables(conn)
        _return_conn(conn)
        self._vouchers: Dict[str, object] = {}
        self._load_all()

    def _load_all(self):
        from voucher.models import Voucher
        from voucher.state import VoucherState
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("SELECT * FROM vouchers")
        for row in cur.fetchall():
            v = self._row_to_voucher(row, cur.description, VoucherState)
            self._vouchers[v.voucher_id] = v
        cur.close()
        _return_conn(conn)

    def _row_to_voucher(self, row, description, VoucherState) -> object:
        from voucher.models import Voucher
        col_names = [d[0] for d in description]
        row_dict = dict(zip(col_names, row))
        return Voucher(
            voucher_id=row_dict.get("voucher_id", ""),
            issuer_wallet=row_dict.get("issuer_wallet", ""),
            agent_id=row_dict.get("agent_id", ""),
            capability_task_type=row_dict.get("capability_task_type", ""),
            unit_price=Decimal(str(row_dict.get("unit_price", "0"))),
            unit_type=row_dict.get("unit_type", ""),
            total_units=row_dict.get("total_units", 0),
            units_used=row_dict.get("units_used", 0),
            total_deposit=Decimal(str(row_dict.get("total_deposit", "0"))),
            channel_id=row_dict.get("channel_id", "mock"),
            chain=row_dict.get("chain", "mock"),
            escrow_id=row_dict.get("escrow_id"),
            state=VoucherState(row_dict.get("state", "issued")),
            created_at=row_dict.get("created_at"),
            activated_at=row_dict.get("activated_at", 0),
            exhausted_at=row_dict.get("exhausted_at", 0),
            cancelled_at=row_dict.get("cancelled_at", 0),
            disputed_at=row_dict.get("disputed_at", 0),
            resolved_at=row_dict.get("resolved_at", 0),
            expires_at=row_dict.get("expires_at", 0),
            dispute_reason=row_dict.get("dispute_reason", ""),
            dispute_initiator=row_dict.get("dispute_initiator", ""),
            resolution=row_dict.get("resolution", ""),
            resolution_reason=row_dict.get("resolution_reason", ""),
        )

    def save(self, voucher) -> None:
        self._vouchers[voucher.voucher_id] = voucher
        conn = _get_conn(self._url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vouchers (
                voucher_id, issuer_wallet, agent_id, capability_task_type,
                unit_price, unit_type, total_units, units_used, total_deposit,
                channel_id, chain, escrow_id, state,
                created_at, activated_at, exhausted_at, cancelled_at,
                disputed_at, resolved_at, expires_at,
                dispute_reason, dispute_initiator, resolution, resolution_reason
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            ) ON CONFLICT(voucher_id) DO UPDATE SET
                units_used=%s, total_deposit=%s, state=%s,
                activated_at=%s, exhausted_at=%s, cancelled_at=%s,
                disputed_at=%s, resolved_at=%s, expires_at=%s,
                dispute_reason=%s, dispute_initiator=%s, resolution=%s, resolution_reason=%s
        """, (
            voucher.voucher_id, voucher.issuer_wallet, voucher.agent_id,
            voucher.capability_task_type, str(voucher.unit_price), voucher.unit_type,
            voucher.total_units, voucher.units_used, str(voucher.total_deposit),
            voucher.channel_id, voucher.chain, voucher.escrow_id,
            voucher.state.value, voucher.created_at, voucher.activated_at,
            voucher.exhausted_at, voucher.cancelled_at, voucher.disputed_at,
            voucher.resolved_at, voucher.expires_at, voucher.dispute_reason,
            voucher.dispute_initiator, voucher.resolution, voucher.resolution_reason,
            # update values
            voucher.units_used, str(voucher.total_deposit), voucher.state.value,
            voucher.activated_at, voucher.exhausted_at, voucher.cancelled_at,
            voucher.disputed_at, voucher.resolved_at, voucher.expires_at,
            voucher.dispute_reason, voucher.dispute_initiator, voucher.resolution, voucher.resolution_reason,
        ))
        conn.commit()
        cur.close()
        _return_conn(conn)

    def get(self, voucher_id: str) -> Optional[object]:
        return self._vouchers.get(voucher_id)

    def get_by_agent(self, agent_id: str) -> List[object]:
        return [v for v in self._vouchers.values() if v.agent_id == agent_id]

    def get_by_issuer(self, issuer_wallet: str) -> List[object]:
        return [v for v in self._vouchers.values() if v.issuer_wallet == issuer_wallet]

    def get_by_state(self, state) -> List[object]:
        return [v for v in self._vouchers.values() if v.state == state]

    def count(self) -> int:
        return len(self._vouchers)
