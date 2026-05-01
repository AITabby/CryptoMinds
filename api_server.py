"""
CryptoMinds API 服务层

将协议暴露为 HTTP API，供 Agent 调用。
"""

from flask import Flask, request, jsonify, g
from decimal import Decimal
import json
import os
import time

from logging_config import setup_logging
setup_logging()

from scripts.env_loader import load_env
_env_config = load_env()

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

# 配置（from env_loader）
API_PORT = _env_config["API_PORT"]
DEBUG_MODE = _env_config["DEBUG"]
INTERNAL_TOKEN = _env_config["INTERNAL_TOKEN"]
MARKET_TASKS = []


import hmac
import logging
from functools import wraps

logger = logging.getLogger(__name__)

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

@app.after_request
def log_request_end(response):
    duration_ms = (time.time() - g.get('_start_time', time.time())) * 1000
    logger.info("request", extra={
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": round(duration_ms, 2),
    })
    return response


def require_internal_token():
    """Require an explicit shared secret for state-mutating internal APIs."""
    if not INTERNAL_TOKEN:
        if os.getenv("CRYPTOMINDS_DEBUG", "false").lower() == "true":
            return True
        return False
    supplied = request.headers.get("X-CryptoMinds-Internal-Token", "")
    if len(supplied) != len(INTERNAL_TOKEN):
        return False
    return hmac.compare_digest(supplied, INTERNAL_TOKEN)


def require_auth(f):
    """Decorator: require internal token for state-mutating endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not require_internal_token():
            return jsonify({"error": "forbidden: internal token required"}), 403
        return f(*args, **kwargs)
    return decorated


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
    from data.sqlite_store import SqliteEscrowStore
    _ensure_initialized()
    _escrow_store = SqliteEscrowStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    _escrow_store.save(order)

    return jsonify({
        "ok": True,
        "escrow_id": escrow_id,
        "state": order.state.value,
        "verification_threshold": order.verification_threshold,
    }), 200


@app.route("/api/v1/escrow/<escrow_id>", methods=["GET"])
def api_escrow_get(escrow_id):
    """获取 Escrow 状态"""
    from data.sqlite_store import SqliteEscrowStore
    _ensure_initialized()
    _escrow_store = SqliteEscrowStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
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
    from data.sqlite_store import SqliteEscrowStore
    _ensure_initialized()
    _escrow_store = SqliteEscrowStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    order = _escrow_store.get(escrow_id)
    if not order:
        return jsonify({"error": f"未知 Escrow: {escrow_id}"}), 404

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
    return jsonify({"ok": True, "state": order.state.value, "escrow_id": escrow_id}), 200


@app.route("/api/v1/escrow/<escrow_id>/resolve", methods=["POST"])
@require_auth
def api_escrow_resolve(escrow_id):
    """管理员仲裁争议"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from data.sqlite_store import SqliteEscrowStore
    _ensure_initialized()
    _escrow_store = SqliteEscrowStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    engine = ArbitrationEngine(_escrow_store, _record_store, AgentRegistry)
    result = engine.resolve_dispute(
        escrow_id=escrow_id,
        arbiter=data.get("arbiter", "admin"),
        decision=data.get("decision", ""),
        reason=data.get("reason", ""),
    )
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/escrow/disputed", methods=["GET"])
def api_escrow_list_disputed():
    """列出所有争议中的 Escrow"""
    from settlement.escrow_state import EscrowState
    from data.sqlite_store import SqliteEscrowStore
    _ensure_initialized()
    _escrow_store = SqliteEscrowStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    orders = _escrow_store.get_by_state(EscrowState.DISPUTED)
    return jsonify({"disputed": [o.to_dict() for o in orders]}), 200


# ── Session Key ─────────────────────────────────────────────

@app.route("/api/v1/session-keys/create", methods=["POST"])
@require_auth
def api_session_key_create():
    """创建 Session Key"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    from auth.session_signer import SessionSigner
    from data.sqlite_store import SqliteSessionKeyStore

    _sk_store = SqliteSessionKeyStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    signer = SessionSigner(_sk_store)

    try:
        sk = signer.create_session_key(
            main_wallet=data.get("main_wallet", ""),
            main_private_key=data.get("main_private_key", ""),
            agent_id=data.get("agent_id", ""),
            chains=data.get("chains", ["bsc"]),
            per_tx_limit=Decimal(str(data.get("per_tx_limit", "1.0"))),
            total_quota=Decimal(str(data.get("total_quota", "10.0"))),
            actions=data.get("actions", ["pay"]),
            validity_seconds=int(data.get("validity_seconds", 86400)),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(sk.to_dict(include_private=True)), 200


@app.route("/api/v1/session-keys/<key_id>", methods=["GET"])
def api_session_key_get(key_id):
    """获取 Session Key 信息"""
    from data.sqlite_store import SqliteSessionKeyStore
    _sk_store = SqliteSessionKeyStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
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
    from data.sqlite_store import SqliteSessionKeyStore
    _sk_store = SqliteSessionKeyStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    signer = SessionSigner(_sk_store)

    result = signer.revoke_session_key(
        session_key_id=key_id,
        main_wallet=data.get("main_wallet", ""),
        main_private_key=data.get("main_private_key", ""),
    )
    if result.get("ok"):
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
    from data.sqlite_store import SqliteSessionKeyStore
    _sk_store = SqliteSessionKeyStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    signer = SessionSigner(_sk_store)

    result = signer.increase_quota(
        session_key_id=key_id,
        additional_quota=Decimal(str(data.get("additional_quota", "0"))),
        main_wallet=data.get("main_wallet", ""),
        main_private_key=data.get("main_private_key", ""),
    )
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/v1/session-keys/agent/<agent_id>", methods=["GET"])
def api_session_keys_by_agent(agent_id):
    """获取 Agent 的活跃 Session Keys"""
    from data.sqlite_store import SqliteSessionKeyStore
    _sk_store = SqliteSessionKeyStore(os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db"))))
    keys = _sk_store.get_by_agent(agent_id)
    return jsonify({"session_keys": [k.to_dict() for k in keys]}), 200

@app.route("/healthz", methods=["GET"])
def health_check():
    """健康检查"""
    checks = {
        "agents": {"registered": len(AgentRegistry._agents)},
        "records": {"total": len(_record_store._records) if hasattr(_record_store, '_records') else 0},
        "channels": {"available": ChannelRegistry.list_all()},
        "gates": {"available": GateRegistry.list_all()},
    }
    return jsonify({
        "status": "ok",
        "version": "2.2.0",
        "timestamp": time.time(),
        "checks": checks,
    })

# ── Prometheus 指标 ────────────────────────────────────

_metrics_counters = {
    "agents_registered": 0,
    "tasks_created": 0,
    "tasks_completed": 0,
    "tasks_verified": 0,
    "credits_issued": 0,
    "agent_buys": 0,
}

@app.route("/metrics", methods=["GET"])
def metrics():
    """Prometheus text format metrics"""
    lines = []
    for name, value in _metrics_counters.items():
        lines.append(f"# TYPE cryptominds_python_{name} counter")
        lines.append(f"cryptominds_python_{name} {value}")
    lines.append(f"# TYPE cryptominds_python_agents_registered gauge")
    lines.append(f"cryptominds_python_agents_online {len(AgentRegistry._agents)}")
    lines.append(f"cryptominds_python_market_tasks {len(MARKET_TASKS)}")
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"}


# ── 启动 ────────────────────────────────────────────

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 服务启动: http://localhost:{port}")
    print(f"协议信息: {json.dumps(get_protocol_info(), indent=2)}")

    if not debug:
        try:
            import gunicorn  # noqa: F401
            print("提示: 生产环境建议使用 gunicorn -b 127.0.0.1:3458 api_server:app")
        except ImportError:
            pass

    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    start_api()
