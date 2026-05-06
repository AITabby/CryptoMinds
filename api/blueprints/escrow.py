# flake8: noqa
"""
CryptoMinds API — Escrow lifecycle blueprint (13 routes)
"""

import os
import sys
import time
from decimal import Decimal

from flask import Blueprint, request, jsonify
from protocol import AgentRegistry

from api.auth import (
    require_auth, verify_admin_secret, _require_wallet_signature,
    _require_wallet_signature_always, _verify_wallet_signature, _is_protected_env,
)
from api.stores import (
    _get_escrow_store as _default_get_escrow_store,
    _get_record_store as _default_get_record_store,
    _write_audit_log as _default_write_audit_log,
)
from api import _increment_metric

escrow_bp = Blueprint("escrow", __name__, url_prefix="/api/v1")


def _compat_callable(name, default):
    facade = sys.modules.get("api_server")
    candidate = getattr(facade, name, None) if facade else None
    return candidate if callable(candidate) else default


def _get_escrow_store():
    return _compat_callable("_get_escrow_store", _default_get_escrow_store)()


def _get_record_store():
    return _compat_callable("_get_record_store", _default_get_record_store)()


def _write_audit_log(*args, **kwargs):
    return _compat_callable("_write_audit_log", _default_write_audit_log)(*args, **kwargs)


def _prepare_multisig_arbitration_call(order, decision: str, reason: str):
    """Return MetaMask params for real on-chain multisig arbitration."""
    arbiter_address = os.getenv("MULTISIG_ARBITER_ADDRESS", "")
    if not arbiter_address:
        return None
    import json
    from pathlib import Path

    abi_path = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "contracts_MultiSigEscrowArbiter_sol_MultiSigEscrowArbiter.abi"
    )
    abi = json.loads(abi_path.read_text()) if abi_path.exists() else []
    return {
        "contract_address": arbiter_address,
        "method": "proposeArbitration",
        "args": [
            order.on_chain_order_id,
            decision == "buyer_win",
            reason,
        ],
        "value": "0",
        "abi": abi,
        "follow_up_method": "confirmArbitration",
        "note": "Submit proposeArbitration from one configured arbiter wallet, then confirmArbitration from another arbiter wallet. Local resolution is recorded only after the multisig transaction executes on-chain.",
    }


@escrow_bp.route("/escrow/create", methods=["POST"])
@require_auth
def api_escrow_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from settlement.escrow_state import EscrowState
    from escrow.models import EscrowOrder

    escrow_id = f"esc-{data.get('buyer_wallet', '')[:8]}-{int(time.time())}"
    order = EscrowOrder(
        escrow_id=escrow_id,
        task_id=data.get("task_id", ""),
        order_id=data.get("order_id", ""),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        seller_agent_id=data.get("seller_agent_id", ""),
        amount=Decimal(str(data.get("amount", "0"))),
        channel_id=data.get("channel_id", "bsc-native"),
        chain=data.get("chain", "bsc"),
        verification_threshold=float(data.get("verification_threshold", 0.7)),
        created_at=int(time.time()),
    )

    _escrow_store = _get_escrow_store()
    _escrow_store.save(order)

    _increment_metric("escrow_created")
    _write_audit_log("escrow_create", wallet=data.get("buyer_wallet", ""),
                     target_id=escrow_id, details={"buyer": data.get("buyer_wallet"), "seller": data.get("seller_wallet"), "amount": str(data.get("amount", 0))})
    return jsonify({
        "ok": True,
        "escrow_id": escrow_id,
        "state": order.state.value,
        "verification_threshold": order.verification_threshold,
    }), 200


@escrow_bp.route("/escrow/<escrow_id>", methods=["GET"])
def api_escrow_get(escrow_id):
    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404
    return jsonify(order.to_dict()), 200


@escrow_bp.route("/escrow/<escrow_id>/dispute", methods=["POST"])
@require_auth
def api_escrow_dispute(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError
    _escrow_store = _get_escrow_store()
    _record_store = _get_record_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    initiator_wallet = data.get("initiator_wallet") or data.get("wallet", "")
    if initiator_wallet.lower() not in (order.buyer_wallet.lower(), order.seller_wallet.lower()):
        return jsonify({"error": "只有买家或卖家可以发起争议"}), 403
    signature_error = _require_wallet_signature_always(data, initiator_wallet, "dispute", escrow_id)
    if signature_error:
        return signature_error

    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("dispute", timestamp=int(time.time()),
                      actor=data.get("initiator", "buyer"),
                      reason=data.get("reason", ""))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.disputed_at = int(time.time())
    order.dispute_reason = data.get("reason", "")
    order.dispute_initiator = data.get("initiator", "buyer")

    from escrow.arbitration import ArbitrationEngine
    engine = ArbitrationEngine(_escrow_store, _record_store, AgentRegistry)
    buyer_w, seller_w = engine.calculate_arbitration_weights(
        order.buyer_wallet, order.seller_agent_id
    )
    order.arbitration_weight_buyer = buyer_w
    order.arbitration_weight_seller = seller_w

    _escrow_store.save(order)
    _increment_metric("escrow_disputed")
    return jsonify({"ok": True, "state": order.state.value, "escrow_id": escrow_id}), 200


@escrow_bp.route("/escrow/<escrow_id>/resolve", methods=["POST"])
def api_escrow_resolve(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    is_admin = False
    admin_error, _ = verify_admin_secret()
    if not admin_error:
        is_admin = True

    arbiter_wallet = data.get("arbiter_wallet", "")
    arbiter_signature = data.get("arbiter_signature", "")
    arbiter_message = data.get("arbiter_message", "")
    arbiter_signatures = data.get("arbiter_signatures", [])
    is_arbiter = False
    confirmed_arbiters = []

    configured_arbiters = [a.strip().lower() for a in os.getenv("ARBITER_WALLETS", "").split(",") if a.strip()]
    required_confirmations = max(2, len(configured_arbiters) // 2 + 1) if configured_arbiters else 2
    decision = data.get("decision", "")

    sigs_to_check = []
    if arbiter_wallet and arbiter_signature and arbiter_message:
        sigs_to_check.append({"wallet": arbiter_wallet, "signature": arbiter_signature, "message": arbiter_message})
    sigs_to_check.extend(arbiter_signatures)

    for sig in sigs_to_check:
        w, s, m = sig.get("wallet", ""), sig.get("signature", ""), sig.get("message", "")
        if not w or not s or not m:
            continue
        expected_prefix = f"CryptoMinds arbitration\nEscrow: {escrow_id}\nDecision: {decision}"
        if not m.startswith(expected_prefix):
            continue
        if _verify_wallet_signature(w, m, s):
            if w.lower() in configured_arbiters:
                confirmed_arbiters.append(w.lower())

    confirmed_arbiters = list(set(confirmed_arbiters))
    if len(confirmed_arbiters) >= required_confirmations:
        is_arbiter = True

    if not is_admin and not is_arbiter:
        return jsonify({"error": "需要管理员密钥 (X-Admin-Secret) 或仲裁员签名"}), 403

    _escrow_store = _get_escrow_store()
    _record_store = _get_record_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404
    from settlement.escrow_state import EscrowState
    if order.state != EscrowState.DISPUTED:
        return jsonify({"error": f"Escrow 状态非 DISPUTED: {order.state.value}"}), 400
    from escrow.arbitration import MINIMUM_ARBITRATION_WAIT_SECONDS
    elapsed = int(time.time()) - order.disputed_at
    if elapsed < MINIMUM_ARBITRATION_WAIT_SECONDS:
        remaining = MINIMUM_ARBITRATION_WAIT_SECONDS - elapsed
        return jsonify({"error": f"仲裁等待期未满: 还需 {remaining} 秒"}), 400

    decision = data.get("decision", "")
    on_chain_result = None

    if order.on_chain_order_id and order.channel_id == "bsc-native":
        if decision == "split":
            return jsonify({"error": "bsc-native 当前不支持链上 split 仲裁，请选择 buyer_win 或 seller_win"}), 400
        if is_arbiter and not is_admin:
            multisig_params = _prepare_multisig_arbitration_call(
                order,
                decision,
                data.get("reason", ""),
            )
            if not multisig_params:
                return jsonify({
                    "error": "MULTISIG_ARBITER_ADDRESS 未配置，不能用仲裁员签名触发链上仲裁",
                }), 409
            return jsonify({
                "ok": True,
                "escrow_id": escrow_id,
                "state": order.state.value,
                "requires_on_chain_multisig_execution": True,
                "confirmed_arbiters": confirmed_arbiters,
                "required_confirmations": required_confirmations,
                "metamask_params": multisig_params,
            }), 202
        admin_key = os.getenv("ADMIN_PRIVATE_KEY", "")
        if not admin_key:
            return jsonify({"error": "ADMIN_PRIVATE_KEY 未配置，不能执行链上仲裁"}), 409

        from settlement.channels.bsc_native import BSCNativeChannel
        channel = BSCNativeChannel()
        if decision == "buyer_win":
            on_chain_result = channel.escrow_refund_on_chain(
                escrow_id=escrow_id,
                on_chain_order_id=order.on_chain_order_id,
                reason=data.get("reason", ""),
                admin_private_key=admin_key,
            )
        elif decision == "seller_win":
            on_chain_result = channel.escrow_confirm_on_chain(
                escrow_id=escrow_id,
                on_chain_order_id=order.on_chain_order_id,
                admin_private_key=admin_key,
            )
        else:
            return jsonify({"error": f"未知仲裁决定: {decision}"}), 400

        if not on_chain_result.success:
            return jsonify({
                "error": "链上仲裁失败，本地状态保持 disputed",
                "details": on_chain_result.error,
            }), 502

    from escrow.arbitration import ArbitrationEngine
    engine = ArbitrationEngine(_escrow_store, _record_store, AgentRegistry)
    result = engine.resolve_dispute(
        escrow_id=escrow_id,
        arbiter=arbiter_wallet if is_arbiter else data.get("arbiter", "admin"),
        decision=decision,
        reason=data.get("reason", ""),
    )
    if result.get("ok"):
        if on_chain_result:
            result["on_chain_tx"] = on_chain_result.tx_hash
        result["arbiter_type"] = "arbiter" if is_arbiter else "admin"
        return jsonify(result), 200
    return jsonify(result), 400


@escrow_bp.route("/escrow/disputed", methods=["GET"])
def api_escrow_list_disputed():
    from settlement.escrow_state import EscrowState
    _escrow_store = _get_escrow_store()
    orders = _escrow_store.get_by_state(EscrowState.DISPUTED)
    return jsonify({"ok": True, "orders": [o.to_dict() for o in orders]}), 200


@escrow_bp.route("/escrow/<escrow_id>/fund/prepare", methods=["POST"])
@require_auth
def api_escrow_fund_prepare(escrow_id):
    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    from settlement.escrow_state import EscrowState
    if order.state != EscrowState.CREATED:
        return jsonify({"error": f"Escrow 状态非 CREATED: {order.state.value}"}), 400

    data = request.get_json() or {}
    from settlement.channels.bsc_native import BSCNativeChannel
    channel = BSCNativeChannel()
    contract_params = channel.escrow_prepare_contract_call(
        action="createOrder",
        seller_address=order.seller_wallet,
        order_id=order.escrow_id,
        amount=order.amount,
        buyer_timeout_seconds=data.get("buyer_timeout_seconds", 86400),
        seller_timeout_seconds=data.get("seller_timeout_seconds", 1800),
    )

    return jsonify({
        "ok": True,
        "escrow_id": escrow_id,
        "state": order.state.value,
        "metamask_params": contract_params,
    }), 200


@escrow_bp.route("/escrow/<escrow_id>/fund/confirm", methods=["POST"])
@require_auth
def api_escrow_fund_confirm(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    on_chain_order_id = data.get("on_chain_order_id", "")
    if _is_protected_env():
        buyer_wallet = data.get("buyer_wallet", order.buyer_wallet)
        signature_error = _require_wallet_signature(data, buyer_wallet, "fund_confirm", escrow_id)
        if signature_error:
            return signature_error
        if buyer_wallet.lower() != order.buyer_wallet.lower():
            return jsonify({"error": "只有买家可以确认锁仓"}), 403
        if order.channel_id == "bsc-native":
            if not on_chain_order_id:
                return jsonify({"error": "缺少链上订单 ID"}), 400
            from settlement.channels.bsc_native import BSCNativeChannel
            chain_order = BSCNativeChannel().escrow_sync_state(on_chain_order_id)
            if chain_order.get("error"):
                return jsonify({"error": f"链上订单校验失败: {chain_order['error']}"}), 400
            if chain_order.get("buyer", "").lower() != order.buyer_wallet.lower():
                return jsonify({"error": "链上买家不匹配"}), 400
            if chain_order.get("seller", "").lower() != order.seller_wallet.lower():
                return jsonify({"error": "链上卖家不匹配"}), 400
            if Decimal(str(chain_order.get("amount", "0"))) != order.amount:
                return jsonify({"error": "链上金额不匹配"}), 400
            if chain_order.get("status_mapped") not in ("funded", "executing", "delivered"):
                return jsonify({"error": f"链上订单状态未锁仓: {chain_order.get('status_mapped')}"}), 400

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError
    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("fund", timestamp=int(time.time()), actor="buyer",
                      reason=data.get("reason", "on-chain createOrder confirmed"))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.funded_at = int(time.time())
    order.on_chain_order_id = on_chain_order_id
    order.seller_timeout_at = int(time.time()) + data.get("seller_timeout_seconds", 1800)

    _escrow_store.save(order)
    return jsonify({"ok": True, "escrow_id": escrow_id, "state": order.state.value}), 200


@escrow_bp.route("/escrow/<escrow_id>/seller-accept", methods=["POST"])
@require_auth
def api_escrow_seller_accept(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    if data.get("seller_wallet", "").lower() != order.seller_wallet.lower():
        return jsonify({"error": "只有卖家可以接单"}), 403
    signature_error = _require_wallet_signature(data, order.seller_wallet, "seller_accept", escrow_id)
    if signature_error:
        return signature_error

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError
    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("seller_accept", timestamp=int(time.time()),
                      actor="seller", reason=data.get("reason", ""))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.seller_timeout_at = int(time.time()) + data.get("seller_timeout_seconds", 1800)
    _escrow_store.save(order)
    return jsonify({"ok": True, "escrow_id": escrow_id, "state": order.state.value}), 200


@escrow_bp.route("/escrow/<escrow_id>/deliver", methods=["POST"])
@require_auth
def api_escrow_deliver(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    if data.get("seller_wallet", "").lower() != order.seller_wallet.lower():
        return jsonify({"error": "只有卖家可以交付"}), 403
    signature_error = _require_wallet_signature(data, order.seller_wallet, "deliver", escrow_id)
    if signature_error:
        return signature_error

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError
    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("deliver", timestamp=int(time.time()),
                      actor="seller", reason=data.get("result", ""))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.delivered_at = int(time.time())
    order.buyer_timeout_at = int(time.time()) + data.get("buyer_timeout_seconds", 86400)
    if data.get("evidence"):
        order.verification_evidence = data.get("evidence", {})

    _escrow_store.save(order)
    return jsonify({"ok": True, "escrow_id": escrow_id, "state": order.state.value}), 200


@escrow_bp.route("/escrow/<escrow_id>/verify", methods=["POST"])
@require_auth
def api_escrow_verify(escrow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError
    if order.state != EscrowState.DELIVERED:
        return jsonify({"error": f"Escrow 状态非 DELIVERED: {order.state.value}"}), 400

    from verification.base import TaskInput, TaskOutput
    from protocol import verify_task
    task_type = data.get("task_type", "token_delivery")
    task_input = TaskInput(
        task_type=task_type,
        buyer_wallet=order.buyer_wallet,
        seller_wallet=order.seller_wallet,
        chain=order.chain,
        amount=order.amount,
    )
    task_output = TaskOutput(
        task_type=task_type,
        seller_wallet=order.seller_wallet,
        tx_hash=data.get("tx_hash", ""),
        token_address=data.get("token_address", ""),
        token_amount=data.get("token_amount", ""),
        data=data.get("data", ""),
        extra=data.get("extra", {}),
    )

    verify_result = verify_task(task_type, task_input, task_output)
    order.verification_score = verify_result.score
    if verify_result.evidence:
        order.verification_evidence = verify_result.evidence

    sm = EscrowStateMachine(order.state)
    now = int(time.time())

    if not verify_result.success:
        try:
            sm.transition("verify_fail", timestamp=now, actor="system",
                          reason=f"verification failed: {verify_result.error}")
        except InvalidTransitionError as e:
            return jsonify({"error": str(e)}), 400
        order.state = sm.state
        order.disputed_at = now
        order.dispute_reason = f"verification failed: {verify_result.error}"
        order.dispute_initiator = "system"
    elif verify_result.score < order.verification_threshold:
        try:
            sm.transition("verify_low_score", timestamp=now, actor="system",
                          reason=f"score {verify_result.score:.2f} < threshold {order.verification_threshold}")
        except InvalidTransitionError as e:
            return jsonify({"error": str(e)}), 400
        order.state = sm.state
        order.disputed_at = now
        order.dispute_reason = f"score {verify_result.score:.2f} < threshold {order.verification_threshold}"
        order.dispute_initiator = "system"
    else:
        try:
            sm.transition("verify_pass", timestamp=now, actor="system",
                          reason=f"score {verify_result.score:.2f} >= threshold {order.verification_threshold}")
        except InvalidTransitionError as e:
            return jsonify({"error": str(e)}), 400
        order.state = sm.state
        order.verified_at = now

    _escrow_store.save(order)
    return jsonify({
        "ok": True,
        "escrow_id": escrow_id,
        "state": order.state.value,
        "verification_score": order.verification_score,
        "verification_result": verify_result.to_dict(),
    }), 200


@escrow_bp.route("/escrow/<escrow_id>/release", methods=["POST"])
@require_auth
def api_escrow_release(escrow_id):
    data = request.get_json() or {}

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    buyer_wallet = data.get("buyer_wallet") or data.get("wallet", "")
    if buyer_wallet.lower() != order.buyer_wallet.lower():
        return jsonify({"error": "只有买家可以确认释放"}), 403
    signature_error = _require_wallet_signature_always(data, order.buyer_wallet, "release", escrow_id)
    if signature_error:
        return signature_error

    if order.channel_id == "bsc-native":
        if not order.on_chain_order_id:
            return jsonify({"error": "缺少链上订单 ID，不能释放"}), 400
        from settlement.channels.bsc_native import BSCNativeChannel
        channel = BSCNativeChannel()
        on_chain_state = channel.escrow_sync_state(order.on_chain_order_id)
        if on_chain_state.get("error"):
            return jsonify({"error": f"链上状态读取失败: {on_chain_state['error']}"}), 502
        if on_chain_state.get("status_mapped") != "released":
            contract_params = channel.escrow_prepare_contract_call(
                action="confirm",
                on_chain_order_id=order.on_chain_order_id,
            )
            return jsonify({
                "ok": True,
                "escrow_id": escrow_id,
                "state": order.state.value,
                "requires_on_chain_confirmation": True,
                "chain_state": on_chain_state.get("status_mapped"),
                "metamask_params": contract_params,
            }), 202

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError
    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("release", timestamp=int(time.time()),
                      actor=data.get("actor", "buyer"),
                      reason=data.get("reason", "verified and confirmed"))
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state

    release_details = {}
    if order.channel_id == "mock":
        from settlement import ChannelRegistry, init_default_channels
        init_default_channels()
        channel = ChannelRegistry.get("mock")
        if channel:
            escrow_result = channel.escrow_release(
                escrow_id=escrow_id,
                to_address=order.seller_wallet,
            )
            if escrow_result.success:
                release_details["tx_hash"] = escrow_result.tx_hash
            else:
                release_details["error"] = escrow_result.error
    elif order.channel_id == "bsc-native" and order.on_chain_order_id:
        release_details["on_chain_order_id"] = order.on_chain_order_id

    _escrow_store.save(order)
    _increment_metric("escrow_released")
    _write_audit_log("escrow_release", wallet=order.buyer_wallet,
                     target_id=escrow_id, result="released")
    response = {"ok": True, "escrow_id": escrow_id, "state": order.state.value}
    if release_details:
        response["release_details"] = release_details
    return jsonify(response), 200


def _execute_chain_claim(order, action):
    if order.channel_id != "bsc-native" or not order.on_chain_order_id:
        return True, None
    admin_key = os.getenv("ADMIN_PRIVATE_KEY", "")
    if not admin_key:
        return False, "ADMIN_PRIVATE_KEY 未配置，无法执行链上 claim"
    try:
        from settlement.channels.bsc_native import BSCNativeChannel
        from web3 import Web3
        channel = BSCNativeChannel()
        if not admin_key.startswith("0x"):
            admin_key = "0x" + admin_key
        result = channel.escrow_prepare_contract_call(
            action=action,
            on_chain_order_id=order.on_chain_order_id,
        )
        if not result.get("method") == action:
            return False, f"合约调用参数异常: {result}"
        contract_address = result["contract_address"]
        abi = result["abi"]
        admin_account = channel.w3.eth.account.from_key(admin_key)
        tx = channel.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi,
        ).functions[action](
            Web3.to_bytes(hexstr=order.on_chain_order_id)
            if order.on_chain_order_id.startswith("0x")
            else Web3.to_bytes(text=order.on_chain_order_id)
        ).build_transaction({
            'from': admin_account.address,
            'nonce': channel.w3.eth.get_transaction_count(admin_account.address),
            'gas': 100000,
            'gasPrice': channel.w3.eth.gas_price,
            'chainId': channel.chain_id,
        })
        signed = channel.w3.eth.account.sign_transaction(tx, admin_key)
        raw_tx = getattr(signed, 'raw_transaction', None) or getattr(signed, 'rawTransaction')
        tx_hash = channel.w3.eth.send_raw_transaction(raw_tx)
        receipt = channel.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status == 1:
            return True, tx_hash.hex()
        return False, f"链上交易 revert: {tx_hash.hex()}"
    except Exception as e:
        return False, str(e)


@escrow_bp.route("/escrow/<escrow_id>/claim-seller-timeout", methods=["POST"])
@require_auth
def api_escrow_claim_seller_timeout(escrow_id):
    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError, EscrowState
    if order.state not in (EscrowState.FUNDED, EscrowState.EXECUTING):
        return jsonify({"error": f"当前状态 {order.state.value} 不支持卖家超时"}), 400

    now = int(time.time())
    if not order.seller_timeout_at or now < order.seller_timeout_at:
        return jsonify({"error": "卖家超时尚未到期或未设置"}), 400

    chain_ok, chain_detail = _execute_chain_claim(order, "claimSellerTimeout")
    if not chain_ok:
        order.chain_synced = False
        _escrow_store.save(order)
        _write_audit_log("escrow_seller_timeout_failed", target_id=escrow_id,
                         wallet=order.seller_wallet, result="chain_claim_failed",
                         details={"error": chain_detail})
        return jsonify({"error": f"链上 claim 失败，本地状态保持不变: {chain_detail}"}), 502

    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("seller_timeout", timestamp=now, actor="system",
                      reason="seller delivery timeout (manual claim)")
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.chain_synced = True
    _escrow_store.save(order)
    _write_audit_log("escrow_seller_timeout", target_id=escrow_id,
                     wallet=order.seller_wallet, result="refunded_timeout")
    response = {"ok": True, "escrow_id": escrow_id, "state": order.state.value}
    if chain_detail:
        response["on_chain_tx"] = chain_detail
    return jsonify(response), 200


@escrow_bp.route("/escrow/<escrow_id>/claim-buyer-timeout", methods=["POST"])
@require_auth
def api_escrow_claim_buyer_timeout(escrow_id):
    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError, EscrowState
    if order.state != EscrowState.DELIVERED:
        return jsonify({"error": f"当前状态 {order.state.value} 不支持买家超时"}), 400

    now = int(time.time())
    if not order.buyer_timeout_at or now < order.buyer_timeout_at:
        return jsonify({"error": "买家超时尚未到期或未设置"}), 400

    chain_ok, chain_detail = _execute_chain_claim(order, "claimBuyerTimeout")
    if not chain_ok:
        order.chain_synced = False
        _escrow_store.save(order)
        _write_audit_log("escrow_buyer_timeout_failed", target_id=escrow_id,
                         wallet=order.buyer_wallet, result="chain_claim_failed",
                         details={"error": chain_detail})
        return jsonify({"error": f"链上 claim 失败，本地状态保持不变: {chain_detail}"}), 502

    sm = EscrowStateMachine(order.state)
    try:
        sm.transition("buyer_timeout", timestamp=now, actor="system",
                      reason="buyer confirmation timeout (manual claim)")
    except InvalidTransitionError as e:
        return jsonify({"error": str(e)}), 400

    order.state = sm.state
    order.chain_synced = True
    _escrow_store.save(order)
    _write_audit_log("escrow_buyer_timeout", target_id=escrow_id,
                     wallet=order.buyer_wallet, result="expired")
    response = {"ok": True, "escrow_id": escrow_id, "state": order.state.value}
    if chain_detail:
        response["on_chain_tx"] = chain_detail
    return jsonify(response), 200
