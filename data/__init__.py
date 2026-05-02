"""Data layer factory — selects PostgreSQL or SQLite based on DATABASE_URL env var."""

import os


def create_stores(db_path: str = None):
    """
    Factory: returns all 6 store instances based on DATABASE_URL env var.

    If DATABASE_URL is set (and starts with postgres:// or postgresql://) → PostgreSQL stores.
    Otherwise → SQLite stores with db_path (dev/demo mode).

    Returns dict: {"record", "credit", "agent_bridge", "escrow", "session_key", "voucher"}
    """
    database_url = os.getenv("DATABASE_URL", "")

    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        from data.pg_store import (
            PgRecordStore, PgCreditStore, PgAgentBridge,
            PgEscrowStore, PgSessionKeyStore, PgVoucherStore,
        )
        return {
            "record": PgRecordStore(database_url),
            "credit": PgCreditStore(database_url),
            "agent_bridge": PgAgentBridge(database_url),
            "escrow": PgEscrowStore(database_url),
            "session_key": PgSessionKeyStore(database_url),
            "voucher": PgVoucherStore(database_url),
        }

    # SQLite fallback
    if not db_path:
        db_path = os.getenv("CRYPTOMINDS_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "web", "cryptominds.db"))

    from data.sqlite_store import (
        SqliteRecordStore, SqliteCreditStore, SqliteAgentBridge,
        SqliteEscrowStore, SqliteSessionKeyStore, SqliteVoucherStore,
    )
    return {
        "record": SqliteRecordStore(db_path),
        "credit": SqliteCreditStore(db_path),
        "agent_bridge": SqliteAgentBridge(db_path),
        "escrow": SqliteEscrowStore(db_path),
        "session_key": SqliteSessionKeyStore(db_path),
        "voucher": SqliteVoucherStore(db_path),
    }