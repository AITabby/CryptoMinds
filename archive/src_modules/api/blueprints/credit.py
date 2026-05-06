# flake8: noqa
"""
CryptoMinds API — Credit currency blueprint (3 routes)
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify

from protocol import issue_credit_currency, list_credit_currencies, accept_credit_currency
from api.auth import require_auth
from api import _increment_metric

credit_bp = Blueprint("credit", __name__, url_prefix="/api/v1")


@credit_bp.route("/credit/issue", methods=["POST"])
@require_auth
def api_issue_credit():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = issue_credit_currency(
        issuer_agent_id=data.get("issuer_agent_id", ""),
        issuer_wallet=data.get("issuer_wallet", ""),
        name=data.get("name", ""),
        symbol=data.get("symbol", ""),
        max_supply=Decimal(str(data.get("max_supply", 0))),
        backed_by=data.get("backed_by", ""),
    )

    if result.get("ok"):
        _increment_metric("credits_issued")
        return jsonify(result), 200
    return jsonify(result), 400


@credit_bp.route("/credit", methods=["GET"])
def api_list_credit():
    return jsonify({"currencies": list_credit_currencies()})


@credit_bp.route("/credit/<currency_id>/accept", methods=["POST"])
@require_auth
def api_accept_credit(currency_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = accept_credit_currency(currency_id, data.get("agent_id", ""))
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400
