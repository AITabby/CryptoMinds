# flake8: noqa
"""
CryptoMinds API — Data store factory + audit log shared across blueprints
"""

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_db_path = os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "cryptominds.db")))
_stores_cache = {}


def _init_stores():
    global _stores_cache
    if not _stores_cache:
        from data import create_stores
        _stores_cache = create_stores(_db_path)
    return _stores_cache


def _get_escrow_store():
    return _init_stores()["escrow"]


def _get_record_store():
    return _init_stores()["record"]


def _get_voucher_store():
    return _init_stores()["voucher"]


def _get_session_key_store():
    return _init_stores()["session_key"]


def _write_audit_log(action: str, agent_id: str = "", wallet: str = "",
                     target_id: str = "", details: dict = None, result: str = ""):
    try:
        database_url = os.getenv("DATABASE_URL", "")
        timestamp = int(time.time())
        details_json = json.dumps(details or {})

        if database_url and database_url.startswith(("postgres://", "postgresql://")):
            from data.pg_store import _get_conn, _return_conn
            conn = _get_conn(database_url)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO audit_log (timestamp, action, agent_id, wallet, target_id, details_json, result) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (timestamp, action, agent_id, wallet, target_id, details_json, result),
            )
            conn.commit()
            cur.close()
            _return_conn(conn)
        else:
            conn = _init_stores()["escrow"]._conn
            conn.execute(
                "INSERT INTO audit_log (timestamp, action, agent_id, wallet, target_id, details_json, result) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (timestamp, action, agent_id, wallet, target_id, details_json, result),
            )
            conn.commit()
    except Exception as e:
        logger.warning("audit log write failed: %s", e)
