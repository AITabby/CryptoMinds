# flake8: noqa
"""
CryptoMinds API — Market tasks + agent buy blueprint (4 routes)
"""

import time
from decimal import Decimal
from flask import Blueprint, request, jsonify

from protocol import agent_buy, find_best_agent
from api.auth import require_auth
from api import _increment_metric

MARKET_TASKS = []

market_bp = Blueprint("market", __name__, url_prefix="/api/v1")


@market_bp.route("/market/tasks", methods=["GET"])
def api_market_tasks_get():
    limit = int(request.args.get("limit", "100"))
    return jsonify({"tasks": MARKET_TASKS[:limit]})


@market_bp.route("/market/tasks", methods=["POST"])
@require_auth
def api_market_tasks_post():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    task = {
        "task_id": data.get("task_id") or f"task-{int(time.time())}-{len(MARKET_TASKS)}",
        "task_type": data.get("task_type", ""),
        "buyer_wallet": data.get("buyer_wallet", ""),
        "amount": str(data.get("amount", 0)),
        "chain": data.get("chain", "bsc"),
        "channel_id": data.get("channel_id", ""),
        "params": data.get("params", {}),
        "created_at": data.get("created_at") or int(time.time()),
        "deadline": data.get("deadline", 0),
    }

    MARKET_TASKS.insert(0, task)
    if len(MARKET_TASKS) > 1000:
        del MARKET_TASKS[1000:]

    return jsonify({"ok": True, "task": task}), 201


@market_bp.route("/agent-buy", methods=["POST"])
@require_auth
def api_agent_buy():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = agent_buy(
        buyer_wallet=data.get("buyer_wallet", ""),
        task_type=data.get("task_type", "token_delivery"),
        amount=Decimal(str(data.get("amount", 0))),
        chain=data.get("chain", "bsc"),
        strategy=data.get("strategy", "balanced"),
    )

    if result.get("ok"):
        _increment_metric("agent_buys")
        return jsonify(result), 200
    return jsonify(result), 400


@market_bp.route("/agents/best-match", methods=["GET"])
def api_best_match():
    task_type = request.args.get("task_type")
    chain = request.args.get("chain", "bsc")
    amount = request.args.get("amount", "0.01")
    strategy = request.args.get("strategy", "balanced")

    if not task_type:
        return jsonify({"error": "缺少 task_type"}), 400

    result = find_best_agent(
        task_type=task_type,
        chain=chain,
        amount=Decimal(amount),
        strategy=strategy,
    )

    if result:
        return jsonify(result), 200
    return jsonify({"error": "没有找到匹配的 Agent"}), 404
