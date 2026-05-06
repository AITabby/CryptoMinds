# flake8: noqa
"""
CryptoMinds API — Task execution blueprint (3 routes)
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify

from protocol import create_task, verify_task, record_task_completion
from verification.base import TaskInput, TaskOutput
from reputation.record import TaskStatus
from api.auth import require_auth
from api import _increment_metric

task_bp = Blueprint("task", __name__, url_prefix="/api/v1")


@task_bp.route("/tasks/create", methods=["POST"])
@require_auth
def api_create_task():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    task_type = data.get("task_type", "")
    if task_type == "compute_result":
        params = data.get("params", {})
        if params.get("compute_type") == "calculation":
            expression = params.get("expression", "")
            if expression and len(expression) > 200:
                return jsonify({"error": "计算表达式过长"}), 400

    result = create_task(
        task_type=data.get("task_type", ""),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        amount=Decimal(str(data.get("amount", 0))),
        chain=data.get("chain", "bsc"),
        channel_id=data.get("channel_id"),
        **data.get("params", {}),
    )

    if result.get("ok"):
        _increment_metric("tasks_created")
        return jsonify(result), 200
    return jsonify(result), 400


@task_bp.route("/tasks/verify", methods=["POST"])
@require_auth
def api_verify_task():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    task_input = TaskInput(
        task_type=data.get("task_type", ""),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        chain=data.get("chain", "bsc"),
        amount=Decimal(str(data.get("amount", 0))),
    )

    task_output = TaskOutput(
        task_type=data.get("task_type", ""),
        seller_wallet=data.get("seller_wallet", ""),
        tx_hash=data.get("tx_hash", ""),
        token_address=data.get("token_address", ""),
        token_amount=data.get("token_amount", ""),
        data=data.get("data", ""),
        extra=data.get("extra", {}),
    )

    result = verify_task(data.get("task_type", ""), task_input, task_output)
    _increment_metric("tasks_verified")
    return jsonify(result.to_dict())


@task_bp.route("/tasks/complete", methods=["POST"])
@require_auth
def api_complete_task():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    status_str = data.get("status", "settled")
    status = TaskStatus(status_str) if status_str in [s.value for s in TaskStatus] else TaskStatus.SETTLED

    result = record_task_completion(
        task_id=data.get("task_id", ""),
        task_type=data.get("task_type", ""),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        seller_agent_id=data.get("seller_agent_id", ""),
        chain=data.get("chain", "bsc"),
        amount=Decimal(str(data.get("amount", 0))),
        status=status,
        score=float(data.get("score", 0)),
        response_time_ms=int(data.get("response_time_ms", 0)),
        payment_tx=data.get("payment_tx", ""),
        payment_amount=Decimal(str(data.get("payment_amount", 0))),
        evidence=data.get("evidence", {}),
    )

    if result.get("ok"):
        _increment_metric("tasks_completed")
        return jsonify(result), 200
    return jsonify(result), 400
