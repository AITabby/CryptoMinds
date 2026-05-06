# flake8: noqa
"""
CryptoMinds API — Health check + metrics blueprint (2 routes)
"""

import os
import time
import logging

from flask import Blueprint, jsonify

from protocol import ChannelRegistry, GateRegistry, AgentRegistry
from api.stores import _get_escrow_store
from api import METRIC_AGENTS_ONLINE, METRIC_MARKET_TASKS, generate_latest, _increment_metric

logger = logging.getLogger(__name__)

BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org")

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
def health_check():
    checks = {
        "status": "ok",
        "agents": {"registered": len(AgentRegistry._agents) if hasattr(AgentRegistry, '_agents') else 0},
        "channels": {"available": ChannelRegistry.list_all()},
        "gates": {"available": GateRegistry.list_all()},
    }

    db_ok = True
    db_error = None
    try:
        store = _get_escrow_store()
        if hasattr(store, 'ping'):
            store.ping()
    except Exception as e:
        db_ok = False
        db_error = str(e)
    checks["database"] = {"status": "ok" if db_ok else "error", "error": db_error}

    rpc_ok = True
    rpc_error = None
    rpc_block = None
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(BSC_RPC, request_kwargs={"timeout": 5}))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        rpc_block = int(w3.eth.block_number)
    except Exception as e:
        rpc_ok = False
        rpc_error = str(e)[:100]
    checks["bsc_rpc"] = {"status": "ok" if rpc_ok else "error", "error": rpc_error, "block_number": rpc_block}

    overall = "ok" if db_ok and rpc_ok else "degraded"
    http_status = 200 if overall == "ok" else 503
    return jsonify({
        "status": overall,
        "version": "2.2.0",
        "timestamp": time.time(),
        "checks": checks,
    }), http_status


@health_bp.route("/metrics", methods=["GET"])
def metrics():
    METRIC_AGENTS_ONLINE.set(len(AgentRegistry._agents))
    from api.blueprints.market import MARKET_TASKS
    METRIC_MARKET_TASKS.set(len(MARKET_TASKS))
    return generate_latest(), 200, {"Content-Type": "text/plain; version=0.0.4"}
