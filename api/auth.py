# flake8: noqa
"""
CryptoMinds API — Auth helpers shared across blueprints
"""

import hmac
import json
import logging
import os
from functools import wraps

from flask import request, jsonify
from scripts.env_loader import load_env

_env_config = load_env()
INTERNAL_TOKEN = _env_config["INTERNAL_TOKEN"]
DEBUG_MODE = _env_config["DEBUG"]
logger = logging.getLogger(__name__)


def _is_demo_mode() -> bool:
    return bool(_env_config.get("DEMO_MODE")) or os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")


def _is_protected_env() -> bool:
    env_name = (_env_config.get("env") or os.getenv("CRYPTOMINDS_ENV", "dev")).lower()
    if DEBUG_MODE or os.getenv("CRYPTOMINDS_DEBUG", "false").lower() in ("1", "true", "yes"):
        return False
    return env_name in ("staging", "prod") or not _is_demo_mode()


def require_internal_token():
    supplied = request.headers.get("X-CryptoMinds-Internal-Token", "")
    if not INTERNAL_TOKEN:
        if _is_protected_env():
            logger.error("INTERNAL_TOKEN 未配置，拒绝受保护环境中的内部 API 请求")
            return False
        if not supplied:
            logger.warning("⚠️ INTERNAL_TOKEN 未配置，API 完全开放！请设置 CRYPTOMINDS_INTERNAL_TOKEN")
            return True
    if len(supplied) != len(INTERNAL_TOKEN):
        return False
    return hmac.compare_digest(supplied, INTERNAL_TOKEN)


def verify_admin_secret():
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret:
        return (jsonify({"error": "管理员认证未配置 (ADMIN_SECRET)"}), 403), None
    supplied = request.headers.get("X-Admin-Secret")
    if not supplied:
        return (jsonify({"error": "需要管理员密钥 (X-Admin-Secret)"}), 403), None
    supplied_buf = supplied.encode("utf-8")
    secret_buf = admin_secret.encode("utf-8")
    if len(supplied_buf) != len(secret_buf) or not hmac.compare_digest(supplied_buf, secret_buf):
        return (jsonify({"error": "管理员密钥错误"}), 403), None
    return None, True


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not require_internal_token():
            return jsonify({"error": "forbidden: internal token required"}), 403
        return f(*args, **kwargs)
    return decorated


def _verify_wallet_signature(wallet: str, message: str, signature: str) -> bool:
    if not wallet or not message or not signature:
        return False
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
        return recovered.lower() == wallet.lower()
    except Exception as exc:
        logger.warning("wallet signature verification failed: %s", exc)
        return False


def _require_wallet_signature(data: dict, wallet: str, action: str, escrow_id: str):
    if not _is_protected_env():
        return None
    message = data.get("message", "")
    signature = data.get("signature", "")
    expected = f"CryptoMinds escrow {action}\nEscrow: {escrow_id}\nWallet: {wallet}"
    if message != expected:
        return jsonify({"error": "签名消息不匹配", "expected_message": expected}), 403
    if not _verify_wallet_signature(wallet, message, signature):
        return jsonify({"error": "钱包签名验证失败"}), 403
    return None


def _require_wallet_signature_always(data: dict, wallet: str, action: str, escrow_id: str):
    message = data.get("message", "")
    signature = data.get("signature", "")
    expected = f"CryptoMinds escrow {action}\nEscrow: {escrow_id}\nWallet: {wallet}"
    if not signature:
        if _is_demo_mode():
            caller_wallet = data.get("wallet", data.get("buyer_wallet", ""))
            if caller_wallet.lower() == wallet.lower():
                return None
        return jsonify({"error": "需要钱包签名", "expected_message": expected}), 403
    if message != expected:
        return jsonify({"error": "签名消息不匹配", "expected_message": expected}), 403
    if not _verify_wallet_signature(wallet, message, signature):
        return jsonify({"error": "钱包签名验证失败"}), 403
    return None


def _require_exact_wallet_signature(data: dict, wallet: str, expected_message: str):
    signature = data.get("signature", "")
    message = data.get("message", "")
    if message != expected_message:
        return jsonify({"error": "签名消息不匹配", "expected_message": expected_message}), 403
    if not _verify_wallet_signature(wallet, message, signature):
        return jsonify({"error": "钱包签名验证失败"}), 403
    return None


def _voucher_message(action: str, voucher_id: str, wallet: str) -> str:
    return f"CryptoMinds voucher {action}\nVoucher: {voucher_id}\nWallet: {wallet}"


def _reject_demo_private_key(main_private_key: str):
    if _is_demo_mode():
        if main_private_key and main_private_key != "0x" + "0" * 64:
            return jsonify({"error": "Demo 模式不允许提供私钥"}), 403
    else:
        if main_private_key:
            return jsonify({"error": "生产环境不允许通过 API 传递私钥"}), 403
    return None
