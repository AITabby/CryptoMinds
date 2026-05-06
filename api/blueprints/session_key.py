# flake8: noqa
"""
CryptoMinds API — Session Key blueprint (5 routes)
"""

import hashlib
import time
from decimal import Decimal

from flask import Blueprint, request, jsonify

from api.auth import (
    require_auth, _require_exact_wallet_signature, _reject_demo_private_key,
    _verify_wallet_signature, _is_protected_env,
)
from api.stores import _get_session_key_store, _write_audit_log
from api import _increment_metric

session_key_bp = Blueprint("session_key", __name__, url_prefix="/api/v1")


@session_key_bp.route("/session-keys/create", methods=["POST"])
@require_auth
def api_session_key_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    from auth.session_key import SessionKey
    _sk_store = _get_session_key_store()

    main_private_key = data.get("main_private_key", "")
    if _is_protected_env():
        if main_private_key:
            return jsonify({"error": "生产环境禁止把主钱包私钥发送到后端，请改用钱包签名授权"}), 400
        now = int(time.time())
        expires_at = int(data.get("expires_at", now + int(data.get("validity_seconds", 86400))))
        if expires_at <= now:
            return jsonify({"error": "Session Key 过期时间必须晚于当前时间"}), 400
        session_address = data.get("session_address", "")
        if not session_address:
            return jsonify({"error": "缺少 session_address"}), 400
        sk = SessionKey(
            session_key_id=hashlib.sha256(
                f"{data.get('main_wallet', '')}:{data.get('agent_id', '')}:{session_address}:{now}".encode()
            ).hexdigest()[:16],
            main_wallet=data.get("main_wallet", ""),
            agent_id=data.get("agent_id", ""),
            available_chains=data.get("chains", ["bsc"]),
            per_tx_limit=Decimal(str(data.get("per_tx_limit", "1.0"))),
            total_quota=Decimal(str(data.get("total_quota", "10.0"))),
            total_used=Decimal("0"),
            callable_actions=data.get("actions", ["pay"]),
            created_at=now,
            expires_at=expires_at,
            nonce=0,
            session_private_key="",
            session_address=session_address,
            authorization_signature=data.get("authorization_signature", data.get("signature", "")),
        )
        signature_error = _require_exact_wallet_signature(
            data,
            sk.main_wallet,
            sk.authorization_message(),
        )
        if signature_error:
            return signature_error
        sk.authorization_signature = data.get("signature", sk.authorization_signature)
        _sk_store.save(sk)
        _increment_metric("session_keys_created")
        _write_audit_log("session_key_create", agent_id=sk.agent_id, wallet=sk.main_wallet,
                         target_id=sk.session_address, details={"chains": sk.available_chains})
        return jsonify(sk.to_dict()), 200

    demo_error = _reject_demo_private_key(main_private_key)
    if demo_error:
        return demo_error
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        import secrets as _secrets
        main_private_key = "0x" + _secrets.token_hex(32)

    signer = SessionSigner(_sk_store)

    try:
        sk = signer.create_session_key(
            main_wallet=data.get("main_wallet", ""),
            main_private_key=main_private_key,
            agent_id=data.get("agent_id", ""),
            chains=data.get("chains", ["bsc"]),
            per_tx_limit=Decimal(str(data.get("per_tx_limit", "1.0"))),
            total_quota=Decimal(str(data.get("total_quota", "10.0"))),
            actions=data.get("actions", ["pay"]),
            validity_seconds=int(data.get("validity_seconds", 86400)),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    _increment_metric("session_keys_created")
    _write_audit_log("session_key_create", agent_id=data.get("agent_id", ""),
                     wallet=data.get("main_wallet", ""), target_id=sk.session_address,
                     details={"chains": data.get("chains", ["bsc"])})
    return jsonify(sk.to_dict()), 200


@session_key_bp.route("/session-keys/<key_id>", methods=["GET"])
@require_auth
def api_session_key_get(key_id):
    _sk_store = _get_session_key_store()
    sk = _sk_store.get(key_id)
    if not sk:
        return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
    return jsonify(sk.to_dict()), 200


@session_key_bp.route("/session-keys/<key_id>/revoke", methods=["POST"])
@require_auth
def api_session_key_revoke(key_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    _sk_store = _get_session_key_store()

    main_private_key = data.get("main_private_key", "")
    if _is_protected_env():
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以撤销 Session Key"}), 403
        expected = f"CryptoMinds revoke session key\nKey: {key_id}\nWallet: {sk.main_wallet}"
        signature_error = _require_exact_wallet_signature(data, sk.main_wallet, expected)
        if signature_error:
            return signature_error
        sk.nonce += 1
        sk.revoked = True
        sk.revoked_at = int(time.time())
        _sk_store.save(sk)
        _increment_metric("session_keys_revoked")
        return jsonify({"ok": True, "nonce": sk.nonce}), 200

    demo_error = _reject_demo_private_key(main_private_key)
    if demo_error:
        return demo_error
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以撤销 Session Key"}), 403
        sig = data.get("signature", "")
        msg = data.get("message", "")
        if sig and msg:
            if not _verify_wallet_signature(sk.main_wallet, msg, sig):
                return jsonify({"error": "钱包签名验证失败"}), 403
        sk.nonce += 1
        sk.revoked = True
        sk.revoked_at = int(time.time())
        _sk_store.save(sk)
        _increment_metric("session_keys_revoked")
        return jsonify({"ok": True, "nonce": sk.nonce}), 200

    signer = SessionSigner(_sk_store)
    result = signer.revoke_session_key(
        session_key_id=key_id,
        main_wallet=data.get("main_wallet", ""),
        main_private_key=main_private_key,
    )
    if result.get("ok"):
        _increment_metric("session_keys_revoked")
        return jsonify(result), 200
    return jsonify(result), 400


@session_key_bp.route("/session-keys/<key_id>/increase-quota", methods=["POST"])
@require_auth
def api_session_key_increase_quota(key_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    _sk_store = _get_session_key_store()

    main_private_key = data.get("main_private_key", "")
    if _is_protected_env():
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以提额"}), 403
        additional = Decimal(str(data.get("additional_quota", "0")))
        expected = (
            f"CryptoMinds increase session key quota\n"
            f"Key: {key_id}\n"
            f"Additional: {additional}\n"
            f"Wallet: {sk.main_wallet}"
        )
        signature_error = _require_exact_wallet_signature(data, sk.main_wallet, expected)
        if signature_error:
            return signature_error
        sk.total_quota += additional
        _sk_store.save(sk)
        return jsonify({"ok": True, "total_quota": str(sk.total_quota)}), 200

    demo_error = _reject_demo_private_key(main_private_key)
    if demo_error:
        return demo_error
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以提额"}), 403
        sig = data.get("signature", "")
        msg = data.get("message", "")
        if sig and msg:
            if not _verify_wallet_signature(sk.main_wallet, msg, sig):
                return jsonify({"error": "钱包签名验证失败"}), 403
        additional = Decimal(str(data.get("additional_quota", "0")))
        sk.total_quota += additional
        _sk_store.save(sk)
        return jsonify({"ok": True, "total_quota": str(sk.total_quota)}), 200

    signer = SessionSigner(_sk_store)
    result = signer.increase_quota(
        session_key_id=key_id,
        additional_quota=Decimal(str(data.get("additional_quota", "0"))),
        main_wallet=data.get("main_wallet", ""),
        main_private_key=main_private_key,
    )
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@session_key_bp.route("/session-keys/agent/<agent_id>", methods=["GET"])
def api_session_keys_by_agent(agent_id):
    _sk_store = _get_session_key_store()
    keys = _sk_store.get_by_agent(agent_id)
    return jsonify({"ok": True, "keys": [k.to_dict() for k in keys]}), 200
