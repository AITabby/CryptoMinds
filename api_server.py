# flake8: noqa
"""
CryptoMinds API 服务层

将协议暴露为 HTTP API，供 Agent 调用。
"""

from flask import Flask, request, jsonify, g
from decimal import Decimal
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from functools import wraps

from logging_config import setup_logging, generate_request_id
setup_logging()
logger = logging.getLogger(__name__)

from scripts.env_loader import load_env
_env_config = load_env()

# Sentry — only initializes if SENTRY_DSN is set
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            release=os.getenv("SENTRY_RELEASE", "cryptoMinds@unknown"),
        )
        logger.info("Sentry initialized")
    except ImportError:
        logger.warning("sentry-sdk not installed — error reporting disabled")

from protocol import (
    get_protocol_info,
    register_agent, search_agents, find_best_agent, agent_buy,
    create_task, verify_task, execute_task,
    record_task_completion, get_agent_reputation, update_agent_reputation,
    get_seller_records, issue_credit_currency, list_credit_currencies,
    accept_credit_currency,
    ChannelRegistry, GateRegistry, AgentRegistry,
)
from agent.capability import AgentCapability, CapabilitySpec, ReputationInfo
from verification.base import TaskInput, TaskOutput
from reputation.record import TaskStatus

# 创建 Flask 应用
app = Flask(__name__)

# Rate limiting — disabled in debug/test mode, enabled in production
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "60")
_is_debug = os.getenv("CRYPTOMINDS_DEBUG", "false").lower() == "true"
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[] if _is_debug else [f"{RATE_LIMIT_PER_MINUTE} per minute"],
    storage_uri="memory://",
)

# 配置（from env_loader）
API_PORT = _env_config["API_PORT"]
DEBUG_MODE = _env_config["DEBUG"]
INTERNAL_TOKEN = _env_config["INTERNAL_TOKEN"]
MARKET_TASKS = []

# ── 请求日志中间件 ──────────────────────────────────────

@app.before_request
def log_request_start():
    g._start_time = time.time()


@app.before_request
def redirect_old_api():
    """Redirect /api/* → /api/v1/* for backwards compatibility."""
    if request.path.startswith("/api/") and not request.path.startswith("/api/v1/"):
        from flask import redirect
        return redirect(f"/api/v1{request.path[4:]}", code=301)

    # Assign request ID for correlation
    g._request_id = request.headers.get("X-Request-ID") or generate_request_id()
    g._start_time = time.time()

@app.after_request
def add_cors_and_log(response):
    # CORS — mirror Express ALLOWED_ORIGINS policy
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
    origin = request.headers.get("Origin", "")
    if allowed_origins == "*":
        response.headers["Access-Control-Allow-Origin"] = "*"
        logger.warning("⚠️ ALLOWED_ORIGINS=* is not safe for production — set specific origins")
    elif origin and origin in allowed_origins.split(","):
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-402-Payment, X-Request-ID"
    # Propagate request ID in response
    request_id = g.get("_request_id", "")
    if request_id:
        response.headers["X-Request-ID"] = request_id
    if request.method == "OPTIONS":
        response.status_code = 204

    # Request logging
    duration_ms = (time.time() - g.get('_start_time', time.time())) * 1000
    # Track HTTP request metrics
    METRIC_HTTP_REQUESTS.labels(method=request.method, path=request.path, status=response.status_code).inc()
    METRIC_HTTP_DURATION.labels(method=request.method, path=request.path).observe(duration_ms / 1000.0)

    logger.info("request", extra={
        "request_id": g.get("_request_id", ""),
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": round(duration_ms, 2),
    })
    return response


def require_internal_token():
    """Require an explicit shared secret for state-mutating internal APIs."""
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
    """Timing-safe admin secret verification. Returns (error_response, None) on failure, (None, True) on success."""
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
    """Decorator: require internal token for state-mutating endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not require_internal_token():
            return jsonify({"error": "forbidden: internal token required"}), 403
        return f(*args, **kwargs)
    return decorated


def _is_demo_mode() -> bool:
    return bool(_env_config.get("DEMO_MODE")) or os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")


def _is_protected_env() -> bool:
    env_name = (_env_config.get("env") or os.getenv("CRYPTOMINDS_ENV", "dev")).lower()
    if DEBUG_MODE or os.getenv("CRYPTOMINDS_DEBUG", "false").lower() in ("1", "true", "yes"):
        return False
    return env_name in ("staging", "prod") or not _is_demo_mode()


def _verify_wallet_signature(wallet: str, message: str, signature: str) -> bool:
    """Verify an EIP-191 personal_sign style wallet signature."""
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
    """Require actor signature outside demo mode; returns Flask error tuple or None."""
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
    """Require actor signature for financial operations regardless of environment mode."""
    message = data.get("message", "")
    signature = data.get("signature", "")
    expected = f"CryptoMinds escrow {action}\nEscrow: {escrow_id}\nWallet: {wallet}"
    if not signature:
        # In demo mode, allow wallet address match as fallback
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
    """Require a wallet signature over an exact canonical message."""
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
    """Reject placeholder private keys in staging/prod or non-demo deployments."""
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        if _is_protected_env():
            return jsonify({"error": "生产/测试网环境不允许使用 DEMO 私钥占位符，请使用钱包签名或真实授权私钥"}), 400
    return None


# ── 协议信息 ────────────────────────────────────────

@app.route("/api/v1/info", methods=["GET"])
def api_info():
    """获取协议信息"""
    return jsonify(get_protocol_info())


@app.route("/api/v1/channels", methods=["GET"])
def api_channels():
    """列出所有结算通道"""
    return jsonify(ChannelRegistry.list_all())


@app.route("/api/v1/gates", methods=["GET"])
def api_gates():
    """列出所有验证门"""
    return jsonify(GateRegistry.list_all())


# ── Agent 管理 ──────────────────────────────────────

@app.route("/api/v1/agents/register", methods=["POST"])
@require_auth
def api_register_agent():
    """注册 Agent"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    # 构造 Agent
    capabilities = []
    for cap in data.get("capabilities", []):
        capabilities.append(CapabilitySpec(
            task_type=cap.get("task_type", ""),
            verification_gate=cap.get("verification_gate", ""),
            supported_chains=cap.get("supported_chains", []),
            supported_channels=cap.get("supported_channels", []),
            params=cap.get("params", {}),
            pricing_model=cap.get("pricing_model", "fixed"),
            base_price=Decimal(str(cap.get("base_price", 0))),
            percentage_rate=Decimal(str(cap.get("percentage_rate", 0))),
            available=cap.get("available", True),
            max_concurrent=cap.get("max_concurrent", 10),
        ))

    reputation = ReputationInfo(
        score=data.get("reputation", {}).get("score", 0),
        tasks_completed=data.get("reputation", {}).get("tasks_completed", 0),
        tasks_failed=data.get("reputation", {}).get("tasks_failed", 0),
        total_volume=Decimal(str(data.get("reputation", {}).get("total_volume", 0))),
    )

    agent = AgentCapability(
        agent_id=data.get("agent_id", ""),
        name=data.get("name", ""),
        description=data.get("description", ""),
        wallet=data.get("wallet", ""),
        endpoint=data.get("endpoint", ""),
        capabilities=capabilities,
        reputation=reputation,
        staked=Decimal(str(data.get("staked", 0))),
        online=data.get("online", True),
    )

    result = register_agent(agent)
    if result.get("ok"):
        _increment_metric("agents_registered")
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/agents", methods=["GET"])
def api_list_agents():
    """列出所有 Agent"""
    task_type = request.args.get("task_type")
    chain = request.args.get("chain")
    amount = request.args.get("amount")
    min_reputation = request.args.get("min_reputation")
    sort_by = request.args.get("sort_by", "reputation")
    limit = int(request.args.get("limit", "10"))

    agents = search_agents(
        task_type=task_type,
        chain=chain,
        amount=Decimal(amount) if amount else None,
        min_reputation=float(min_reputation) if min_reputation else None,
        sort_by=sort_by,
        limit=limit,
    )

    return jsonify({"agents": agents})


@app.route("/api/v1/agents/<agent_id>", methods=["GET"])
def api_get_agent(agent_id):
    """获取 Agent 信息"""
    agent = AgentRegistry.get(agent_id)
    if agent:
        return jsonify(agent.to_dict())
    return jsonify({"error": f"未知 Agent: {agent_id}"}), 404


@app.route("/api/v1/agents/<agent_id>/reputation", methods=["GET"])
def api_get_reputation(agent_id):
    """获取 Agent 信誉分"""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404

    rep = get_agent_reputation(agent_id, agent.wallet)
    return jsonify(rep)


@app.route("/api/v1/agents/<agent_id>/reputation/update", methods=["POST"])
@require_auth
def api_update_reputation(agent_id):
    """更新 Agent 信誉分"""
    result = update_agent_reputation(agent_id)
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/agents/<agent_id>/records", methods=["GET"])
def api_get_records(agent_id):
    """获取 Agent 履约记录"""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404

    limit = int(request.args.get("limit", "100"))
    records = get_seller_records(agent.wallet, limit)
    return jsonify({"records": records})


# ── 任务执行 ────────────────────────────────────────

@app.route("/api/v1/tasks/create", methods=["POST"])
@require_auth
def api_create_task():
    """创建任务"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    # Validate compute expressions at API boundary
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


@app.route("/api/v1/tasks/verify", methods=["POST"])
@require_auth
def api_verify_task():
    """验证任务"""
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


@app.route("/api/v1/tasks/complete", methods=["POST"])
@require_auth
def api_complete_task():
    """记录任务完成"""
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


# ── 市场任务 ────────────────────────────────────────

@app.route("/api/v1/market/tasks", methods=["GET"])
def api_market_tasks_get():
    """Agent 市场任务队列（读取）"""
    limit = int(request.args.get("limit", "100"))
    return jsonify({"tasks": MARKET_TASKS[:limit]})


@app.route("/api/v1/market/tasks", methods=["POST"])
@require_auth
def api_market_tasks_post():
    """Agent 市场任务队列（发布）"""
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


# ── Agent 自主下单 ──────────────────────────────────

@app.route("/api/v1/agent-buy", methods=["POST"])
@require_auth
def api_agent_buy():
    """Agent 自主下单"""
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


@app.route("/api/v1/agents/best-match", methods=["GET"])
def api_best_match():
    """找到最佳匹配的 Agent"""
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


# ── 信用货币 ────────────────────────────────────────

@app.route("/api/v1/credit/issue", methods=["POST"])
@require_auth
@limiter.shared_limit("5 per minute", scope="credit-issue")
def api_issue_credit():
    """发行信用货币"""
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


@app.route("/api/v1/credit", methods=["GET"])
def api_list_credit():
    """列出所有信用货币"""
    return jsonify({"currencies": list_credit_currencies()})


@app.route("/api/v1/credit/<currency_id>/accept", methods=["POST"])
@require_auth
def api_accept_credit(currency_id):
    """接受信用货币"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = accept_credit_currency(currency_id, data.get("agent_id", ""))
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


# ── Escrow 托管 ────────────────────────────────────────────

# ── Data store factory ──────────────────────────────────────
# Uses DATABASE_URL env var to select PostgreSQL or SQLite backend
# If DATABASE_URL starts with postgres:// → PG stores, otherwise → SQLite

_db_path = os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db")))
_stores_cache = {}


def _init_stores():
    """Initialize store instances via factory. Cached at module level."""
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
    """Write an audit log entry to the database (SQLite or PostgreSQL)."""
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

@app.route("/api/v1/escrow/create", methods=["POST"])
@require_auth
def api_escrow_create():
    """创建 Escrow 托管订单"""
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

    # Save to SQLite
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


@app.route("/api/v1/escrow/<escrow_id>", methods=["GET"])
def api_escrow_get(escrow_id):
    """获取 Escrow 状态"""
    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404
    return jsonify(order.to_dict()), 200


@app.route("/api/v1/escrow/<escrow_id>/dispute", methods=["POST"])
@require_auth
def api_escrow_dispute(escrow_id):
    """进入争议"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError
    _escrow_store = _get_escrow_store()
    _record_store = _get_record_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    # Always verify dispute initiator authorization
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

    # 计算仲裁权重
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


@app.route("/api/v1/escrow/<escrow_id>/resolve", methods=["POST"])
@limiter.shared_limit("10 per minute", scope="admin")
def api_escrow_resolve(escrow_id):
    """仲裁争议 — 支持 X-Admin-Secret（单管理员）或 arbiter_wallet 签名（多签）"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    # Check auth: admin secret OR arbiter wallet signature
    is_admin = False
    admin_error, _ = verify_admin_secret()
    if not admin_error:
        is_admin = True

    arbiter_wallet = data.get("arbiter_wallet", "")
    arbiter_signature = data.get("arbiter_signature", "")
    arbiter_message = data.get("arbiter_message", "")
    arbiter_signatures = data.get("arbiter_signatures", [])  # [{wallet, signature, message}, ...]
    is_arbiter = False
    confirmed_arbiters = []

    configured_arbiters = [a.strip().lower() for a in os.getenv("ARBITER_WALLETS", "").split(",") if a.strip()]
    required_confirmations = max(2, len(configured_arbiters) // 2 + 1) if configured_arbiters else 2
    decision = data.get("decision", "")

    # Collect valid arbiter signatures — multi-sig: require M-of-N
    # Support both single arbiter_wallet/signature and arbiter_signatures array
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

    # Deduplicate — same arbiter signing twice doesn't count
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


@app.route("/api/v1/escrow/disputed", methods=["GET"])
def api_escrow_list_disputed():
    """列出所有争议中的 Escrow"""
    from settlement.escrow_state import EscrowState
    _escrow_store = _get_escrow_store()
    orders = _escrow_store.get_by_state(EscrowState.DISPUTED)
    return jsonify({"ok": True, "orders": [o.to_dict() for o in orders]}), 200


# ── Escrow 正向路径 (生命周期端点) ────────────────────────────

@app.route("/api/v1/escrow/<escrow_id>/fund/prepare", methods=["POST"])
@require_auth
def api_escrow_fund_prepare(escrow_id):
    """返回 MetaMask 合约调用参数，用于链上 createOrder"""
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


@app.route("/api/v1/escrow/<escrow_id>/fund/confirm", methods=["POST"])
@require_auth
def api_escrow_fund_confirm(escrow_id):
    """链上 createOrder 确认后，CREATED → FUNDED"""
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


@app.route("/api/v1/escrow/<escrow_id>/seller-accept", methods=["POST"])
@require_auth
def api_escrow_seller_accept(escrow_id):
    """卖家接单，FUNDED → EXECUTING"""
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


@app.route("/api/v1/escrow/<escrow_id>/deliver", methods=["POST"])
@require_auth
def api_escrow_deliver(escrow_id):
    """卖家交付结果，EXECUTING → DELIVERED"""
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


@app.route("/api/v1/escrow/<escrow_id>/verify", methods=["POST"])
@require_auth
def api_escrow_verify(escrow_id):
    """运行验证门，DELIVERED → VERIFIED 或 DISPUTED (三分支)"""
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


@app.route("/api/v1/escrow/<escrow_id>/release", methods=["POST"])
@require_auth
def api_escrow_release(escrow_id):
    """释放资金给卖家，VERIFIED → RELEASED"""
    data = request.get_json() or {}

    _escrow_store = _get_escrow_store()
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

    # Always require buyer authorization for escrow release
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
    """Execute on-chain timeout claim. Returns (success, tx_hash_or_error)."""
    if order.channel_id != "bsc-native" or not order.on_chain_order_id:
        return True, None  # no on-chain component
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
            'chainId': 56,
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


@app.route("/api/v1/escrow/<escrow_id>/claim-seller-timeout", methods=["POST"])
@require_auth
def api_escrow_claim_seller_timeout(escrow_id):
    """卖家超时，FUNDED/EXECUTING → REFUNDED_TIMEOUT（链上优先）"""
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

    # Chain first: if on-chain order exists, execute claim before changing local state
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


@app.route("/api/v1/escrow/<escrow_id>/claim-buyer-timeout", methods=["POST"])
@require_auth
def api_escrow_claim_buyer_timeout(escrow_id):
    """买家确认超时，DELIVERED → EXPIRED（链上优先）"""
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

    # Chain first: if on-chain order exists, execute claim before changing local state
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


# ── Voucher 按量计费 ──────────────────────────────────────────

@app.route("/api/v1/voucher/create", methods=["POST"])
@require_auth
def api_voucher_create():
    """创建 Voucher (按量计费预付订单)"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from voucher.models import Voucher
    from voucher.state import VoucherState
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


@app.route("/api/v1/voucher/<voucher_id>", methods=["GET"])
@require_auth
def api_voucher_get(voucher_id):
    """获取 Voucher 信息"""
    _voucher_store = _get_voucher_store()
    voucher = _voucher_store.get(voucher_id)
    if not voucher:
        return jsonify({"error": f"未知 Voucher: {voucher_id}"}), 404
    return jsonify(voucher.to_dict()), 200


@app.route("/api/v1/voucher/<voucher_id>/activate", methods=["POST"])
@require_auth
def api_voucher_activate(voucher_id):
    """激活 Voucher (ISSUED → ACTIVE)"""
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


@app.route("/api/v1/voucher/<voucher_id>/use", methods=["POST"])
@require_auth
def api_voucher_use(voucher_id):
    """消费一个单位 (ACTIVE, units_used++)"""
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

    # 自动耗尽检查
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
        # use transition (stay ACTIVE)
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


@app.route("/api/v1/voucher/<voucher_id>/dispute", methods=["POST"])
@require_auth
def api_voucher_dispute(voucher_id):
    """发起争议 (ACTIVE → DISPUTED)"""
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


@app.route("/api/v1/voucher/<voucher_id>/resolve", methods=["POST"])
@limiter.shared_limit("10 per minute", scope="admin")
def api_voucher_resolve(voucher_id):
    """管理员仲裁争议"""
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


@app.route("/api/v1/voucher/agent/<agent_id>", methods=["GET"])
@require_auth
def api_voucher_list_by_agent(agent_id):
    """列出 Agent 的 Vouchers"""
    _voucher_store = _get_voucher_store()
    vouchers = _voucher_store.get_by_agent(agent_id)
    return jsonify({"ok": True, "vouchers": [v.to_dict() for v in vouchers]}), 200


# ── Session Key ─────────────────────────────────────────────

@app.route("/api/v1/session-keys/create", methods=["POST"])
@require_auth
def api_session_key_create():
    """创建 Session Key"""
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

    # Demo/dev mode: generate a random private key if placeholder passed
    demo_error = _reject_demo_private_key(main_private_key)
    if demo_error:
        return demo_error
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        import secrets as _secrets
        main_private_key = "0x" + _secrets.token_hex(32)

    _sk_store = _get_session_key_store()
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


@app.route("/api/v1/session-keys/<key_id>", methods=["GET"])
@require_auth
def api_session_key_get(key_id):
    """获取 Session Key 信息"""
    _sk_store = _get_session_key_store()
    sk = _sk_store.get(key_id)
    if not sk:
        return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
    return jsonify(sk.to_dict()), 200


@app.route("/api/v1/session-keys/<key_id>/revoke", methods=["POST"])
@require_auth
def api_session_key_revoke(key_id):
    """撤销 Session Key"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    _sk_store = _get_session_key_store()
    signer = SessionSigner(_sk_store)

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
    # Require wallet signature for revocation (no raw private key in request)
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        # In demo mode: verify wallet address matches + optional signature
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以撤销 Session Key"}), 403
        # Still require a valid signature if provided, even in demo
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

    result = signer.revoke_session_key(
        session_key_id=key_id,
        main_wallet=data.get("main_wallet", ""),
        main_private_key=main_private_key,
    )
    if result.get("ok"):
        _increment_metric("session_keys_revoked")
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/session-keys/<key_id>/increase-quota", methods=["POST"])
@require_auth
def api_session_key_increase_quota(key_id):
    """增加 Session Key 总额度"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    _sk_store = _get_session_key_store()
    signer = SessionSigner(_sk_store)

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
    # Require wallet signature for quota increase (no raw private key in request)
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        sk = _sk_store.get(key_id)
        if not sk:
            return jsonify({"error": f"未知 Session Key: {key_id}"}), 404
        if data.get("main_wallet", "").lower() != sk.main_wallet.lower():
            return jsonify({"error": "只有主钱包可以提额"}), 403
        # Still require a valid signature if provided, even in demo
        sig = data.get("signature", "")
        msg = data.get("message", "")
        if sig and msg:
            if not _verify_wallet_signature(sk.main_wallet, msg, sig):
                return jsonify({"error": "钱包签名验证失败"}), 403
        additional = Decimal(str(data.get("additional_quota", "0")))
        sk.total_quota += additional
        _sk_store.save(sk)
        return jsonify({"ok": True, "total_quota": str(sk.total_quota)}), 200

    result = signer.increase_quota(
        session_key_id=key_id,
        additional_quota=Decimal(str(data.get("additional_quota", "0"))),
        main_wallet=data.get("main_wallet", ""),
        main_private_key=main_private_key,
    )
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/session-keys/agent/<agent_id>", methods=["GET"])
def api_session_keys_by_agent(agent_id):
    """获取 Agent 的活跃 Session Keys"""
    _sk_store = _get_session_key_store()
    keys = _sk_store.get_by_agent(agent_id)
    return jsonify({"ok": True, "keys": [k.to_dict() for k in keys]}), 200

@app.route("/healthz", methods=["GET"])
@limiter.exempt
def health_check():
    """健康检查 — includes DB and BSC RPC connectivity"""
    checks = {
        "status": "ok",
        "agents": {"registered": len(AgentRegistry._agents) if hasattr(AgentRegistry, '_agents') else 0},
        "channels": {"available": ChannelRegistry.list_all()},
        "gates": {"available": GateRegistry.list_all()},
    }

    # Check database connectivity
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

    # Check BSC RPC connectivity
    rpc_ok = True
    rpc_error = None
    rpc_block = None
    try:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(BSC_RPC, request_kwargs={"timeout": 5}))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        rpc_block = w3.eth.block_number
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

# ── Prometheus 指标 (prometheus_client) ────────────────────────────────────

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Business counters
METRIC_AGENTS_REGISTERED = Counter("cryptominds_python_agents_registered", "Agents registered")
METRIC_TASKS_CREATED = Counter("cryptominds_python_tasks_created", "Tasks created")
METRIC_TASKS_COMPLETED = Counter("cryptominds_python_tasks_completed", "Tasks completed")
METRIC_TASKS_VERIFIED = Counter("cryptominds_python_tasks_verified", "Tasks verified")
METRIC_CREDITS_ISSUED = Counter("cryptominds_python_credits_issued", "Credits issued")
METRIC_AGENT_BUYS = Counter("cryptominds_python_agent_buys", "Agent buy operations")
METRIC_ESCROW_CREATED = Counter("cryptominds_python_escrow_created", "Escrow orders created")
METRIC_ESCROW_DISPUTED = Counter("cryptominds_python_escrow_disputed", "Escrow orders disputed")
METRIC_ESCROW_RELEASED = Counter("cryptominds_python_escrow_released", "Escrow orders released")
METRIC_SESSION_KEYS_CREATED = Counter("cryptominds_python_session_keys_created", "Session keys created")
METRIC_SESSION_KEYS_REVOKED = Counter("cryptominds_python_session_keys_revoked", "Session Keys revoked")
METRIC_VOUCHERS_CREATED = Counter("cryptominds_python_vouchers_created", "Vouchers created")
METRIC_VOUCHERS_ACTIVATED = Counter("cryptominds_python_vouchers_activated", "Vouchers activated")
METRIC_VOUCHERS_EXHAUSTED = Counter("cryptominds_python_vouchers_exhausted", "Vouchers exhausted")

# Gauges
METRIC_AGENTS_ONLINE = Gauge("cryptominds_python_agents_online", "Agents currently online")
METRIC_MARKET_TASKS = Gauge("cryptominds_python_market_tasks", "Tasks in the market")

# HTTP request metrics
METRIC_HTTP_REQUESTS = Counter(
    "cryptominds_python_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
METRIC_HTTP_DURATION = Histogram(
    "cryptominds_python_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0],
)

# Map of metric names to prometheus_client objects
_METRIC_MAP = {
    "agents_registered": METRIC_AGENTS_REGISTERED,
    "tasks_created": METRIC_TASKS_CREATED,
    "tasks_completed": METRIC_TASKS_COMPLETED,
    "tasks_verified": METRIC_TASKS_VERIFIED,
    "credits_issued": METRIC_CREDITS_ISSUED,
    "agent_buys": METRIC_AGENT_BUYS,
    "escrow_created": METRIC_ESCROW_CREATED,
    "escrow_disputed": METRIC_ESCROW_DISPUTED,
    "escrow_released": METRIC_ESCROW_RELEASED,
    "session_keys_created": METRIC_SESSION_KEYS_CREATED,
    "session_keys_revoked": METRIC_SESSION_KEYS_REVOKED,
    "vouchers_created": METRIC_VOUCHERS_CREATED,
    "vouchers_activated": METRIC_VOUCHERS_ACTIVATED,
    "vouchers_exhausted": METRIC_VOUCHERS_EXHAUSTED,
}


def _increment_metric(name: str):
    metric = _METRIC_MAP.get(name)
    if metric:
        metric.inc()

@app.route("/metrics", methods=["GET"])
@limiter.exempt
def metrics():
    """Prometheus metrics endpoint — uses prometheus_client library."""
    # Update gauges before generating output
    METRIC_AGENTS_ONLINE.set(len(AgentRegistry._agents))
    METRIC_MARKET_TASKS.set(len(MARKET_TASKS))
    return generate_latest(), 200, {"Content-Type": "text/plain; version=0.0.4"}


# ── 启动 ────────────────────────────────────────────

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 服务启动: http://localhost:{port}")
    print(f"协议信息: {json.dumps(get_protocol_info(), indent=2)}")

    # Start SQLite backup thread
    db_path = os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db")))
    from data.sqlite_store import start_backup_thread, register_shutdown_checkpoint
    start_backup_thread(db_path)
    register_shutdown_checkpoint(db_path)

    # Start Escrow Watchdog (auto-trigger timeout state transitions)
    from escrow.watchdog import EscrowWatchdog
    _watchdog = EscrowWatchdog(
        _get_escrow_store(),
        _get_record_store(),
        AgentRegistry,
        check_interval=int(os.getenv("WATCHDOG_INTERVAL", "60")),
    )
    _watchdog.start()

    # Production: use gunicorn if available and not in debug mode
    if not debug:
        try:
            from gunicorn.app.base import BaseApplication

            class StandaloneApplication(BaseApplication):
                def __init__(self, app_obj, options=None):
                    self.options = options or {}
                    self.application = app_obj
                    super().__init__()

                def load_config(self):
                    for key, value in self.options.items():
                        if key in self.cfg.settings and value is not None:
                            self.cfg.set(key.lower(), value)

                def load(self):
                    return self.application

            options = {
                "bind": f"{os.getenv('GUNICORN_HOST', '0.0.0.0')}:{port}",
                "workers": int(os.getenv("GUNICORN_WORKERS", "2")),
                "threads": int(os.getenv("GUNICORN_THREADS", "4")),
                "timeout": 120,
                "accesslog": "-",
                "errorlog": "-",
            }
            print(
                f"[production] gunicorn启动: bind={options['bind']}, "
                f"workers={options['workers']}, threads={options['threads']}"
            )
            StandaloneApplication(app, options).run()
            return
        except ImportError:
            print("[CRITICAL] gunicorn未安装 — Flask开发服务器不适合生产环境!")
            print("[CRITICAL] 安装: pip install gunicorn")
            if os.getenv("CRYPTOMINDS_DEBUG", "false").lower() != "true":
                sys.exit(1)
            print("[warning] debug模式, 继续使用Flask dev server")

    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    start_api()
