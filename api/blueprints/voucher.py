# flake8: noqa
"""
CryptoMinds API — Voucher blueprint (7 routes)
"""

import time
from decimal import Decimal

from flask import Blueprint, request, jsonify

from api.auth import (
    require_auth, verify_admin_secret, _require_exact_wallet_signature,
    _voucher_message, _is_protected_env,
)
from api.stores import _get_voucher_store, _write_audit_log
from api import _increment_metric

voucher_bp = Blueprint("voucher", __name__, url_prefix="/api/v1")


@voucher_bp.route("/voucher/create", methods=["POST"])
@require_auth
def api_voucher_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from voucher.models import Voucher
    from decimal import Decimal as D

    unit_price = D(str(data.get("unit_price", "0")))
    total_units = int(data.get("total_units", 0))
    total_deposit = unit_price * total_units
    issuer_wallet = data.get("issuer_wallet", "")
    if _is_protected_env():
        expected = (
            "CryptoMinds voucher create\n"
            f"Issuer: {issuer_wallet}\n"
            f"Agent: {data.get('agent_id', '')}\n"
            f"TaskType: {data.get('capability_task_type', '')}\n"
            f"UnitPrice: {unit_price}\n"
            f"TotalUnits: {total_units}"
        )
        signature_error = _require_exact_wallet_signature(data, issuer_wallet, expected)
        if signature_error:
            return signature_error

    voucher_id = f"vch-{data.get('issuer_wallet', '')[:8]}-{int(time.time())}"
    voucher = Voucher(
        voucher_id=voucher_id,
        issuer_wallet=issuer_wallet,
        agent_id=data.get("agent_id", ""),
        capability_task_type=data.get("capability_task_type", ""),
        unit_price=unit_price,
        unit_type=data.get("unit_type", "api_call"),
        total_units=total_units,
        total_deposit=total_deposit,
        channel_id=data.get("channel_id", "mock"),
        chain=data.get("chain", "mock"),
        escrow_id=data.get("escrow_id"),
        expires_at=data.get("expires_at", 0),
    )

    _voucher_store = _get_voucher_store()
    _voucher_store.save(voucher)
    _increment_metric("vouchers_created")
    return jsonify({"ok": True, "voucher_id": voucher_id, "state": voucher.state.value, "total_units": total_units, "total_deposit": str(total_deposit)}), 200


@voucher_bp.route("/voucher/<voucher_id>", methods=["GET"])
@require_auth
def api_voucher_get(voucher_id):
    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404
    return jsonify(voucher.to_dict()), 200


@voucher_bp.route("/voucher/<voucher_id>/activate", methods=["POST"])
@require_auth
def api_voucher_activate(voucher_id):
    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404
    if _is_protected_env():
        signature_error = _require_exact_wallet_signature(
            request.get_json() or {},
            voucher.issuer_wallet,
            _voucher_message("activate", voucher_id, voucher.issuer_wallet),
        )
        if signature_error:
            return signature_error

    from voucher.state import VoucherStateMachine, InvalidTransitionError
    sm = VoucherStateMachine(voucher.state)
    try:
        sm.transition("activate", timestamp=int(time.time()), actor="buyer")
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    voucher.state = sm.state
    voucher.activated_at = int(time.time())
    _voucher_store.save(voucher)
    _increment_metric("vouchers_activated")
    return jsonify({"ok": True, "voucher_id": voucher_id, "state": voucher.state.value}), 200


@voucher_bp.route("/voucher/<voucher_id>/use", methods=["POST"])
@require_auth
def api_voucher_use(voucher_id):
    data = request.get_json() or {}
    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404
    if _is_protected_env():
        expected = (
            f"{_voucher_message('use', voucher_id, voucher.issuer_wallet)}\n"
            f"Units: {int(data.get('units', 1))}"
        )
        signature_error = _require_exact_wallet_signature(data, voucher.issuer_wallet, expected)
        if signature_error:
            return signature_error

    from voucher.state import VoucherStateMachine, InvalidTransitionError, VoucherState
    units = int(data.get("units", 1))

    if voucher.state != VoucherState.ACTIVE:
        return jsonify({"error": f"Voucher 状态非 ACTIVE: {voucher.state.value}"}), 400

    new_used = voucher.units_used + units
    if new_used > voucher.total_units:
        return jsonify({"error": f"超额使用: {new_used} > {voucher.total_units}"}), 400

    voucher.units_used = new_used

    if voucher.units_used >= voucher.total_units:
        sm = VoucherStateMachine(voucher.state)
        try:
            sm.transition("exhaust", timestamp=int(time.time()), actor="system")
        except InvalidTransitionError:
            pass
        voucher.state = sm.state
        voucher.exhausted_at = int(time.time())
        _increment_metric("vouchers_exhausted")
    else:
        sm = VoucherStateMachine(voucher.state)
        try:
            sm.transition("use", timestamp=int(time.time()), actor=data.get("actor", "buyer"))
        except InvalidTransitionError:
            pass

    _voucher_store.save(voucher)
    return jsonify({
        "ok": True,
        "voucher_id": voucher_id,
        "state": voucher.state.value,
        "units_used": voucher.units_used,
        "units_remaining": voucher.units_remaining,
    }), 200


@voucher_bp.route("/voucher/<voucher_id>/dispute", methods=["POST"])
@require_auth
def api_voucher_dispute(voucher_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404
    if _is_protected_env():
        initiator_wallet = data.get("initiator_wallet") or data.get("wallet", "")
        if initiator_wallet.lower() != voucher.issuer_wallet.lower():
            return jsonify({"error": "只有 Voucher 发行钱包可以发起争议"}), 403
        signature_error = _require_exact_wallet_signature(
            data,
            voucher.issuer_wallet,
            _voucher_message("dispute", voucher_id, voucher.issuer_wallet),
        )
        if signature_error:
            return signature_error

    from voucher.state import VoucherStateMachine, InvalidTransitionError
    sm = VoucherStateMachine(voucher.state)
    try:
        sm.transition("dispute", timestamp=int(time.time()),
                      actor=data.get("initiator", "buyer"),
                      reason=data.get("reason", ""))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    voucher.state = sm.state
    voucher.disputed_at = int(time.time())
    voucher.dispute_reason = data.get("reason", "")
    voucher.dispute_initiator = data.get("initiator", "buyer")
    _voucher_store.save(voucher)
    return jsonify({"ok": True, "voucher_id": voucher_id, "state": voucher.state.value}), 200


@voucher_bp.route("/voucher/<voucher_id>/resolve", methods=["POST"])
def api_voucher_resolve(voucher_id):
    error, _ = verify_admin_secret()
    if error:
        return error

    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404

    from voucher.state import VoucherStateMachine, InvalidTransitionError
    sm = VoucherStateMachine(voucher.state)
    decision = data.get("decision", "")
    if decision == "buyer_win":
        try:
            sm.transition("arbitrate_buyer_win", timestamp=int(time.time()), actor="admin")
        except InvalidTransitionError as e:
            return jsonify({"error": str(e)}), 400
        voucher.resolution = "buyer_win"
    elif decision in ("seller_win", "split"):
        try:
            sm.transition("arbitrate_seller_win", timestamp=int(time.time()), actor="admin")
        except InvalidTransitionError as e:
            return jsonify({"error": str(e)}), 400
        voucher.resolution = decision
    else:
        return jsonify({"error": f"未知仲裁决定: {decision}"}), 400

    voucher.state = sm.state
    voucher.resolved_at = int(time.time())
    voucher.resolution_reason = data.get("reason", "")
    _voucher_store.save(voucher)
    return jsonify({"ok": True, "voucher_id": voucher_id, "state": voucher.state.value, "resolution": voucher.resolution}), 200


@voucher_bp.route("/voucher/agent/<agent_id>", methods=["GET"])
@require_auth
def api_voucher_list_by_agent(agent_id):
    _voucher_store = _get_voucher_store()
    vouchers = _voucher_store.get_by_agent(agent_id)
    return jsonify({"ok": True, "vouchers": [v.to_dict() for v in vouchers]}), 200
