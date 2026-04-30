"""
CryptoMinds API 服务层

将协议暴露为 HTTP API，供 Agent 调用。
"""

from flask import Flask, request, jsonify
from decimal import Decimal
import json
import os

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

# 配置
API_PORT = int(os.getenv("CRYPTOMINDS_API_PORT", "3458"))
DEBUG_MODE = os.getenv("CRYPTOMINDS_DEBUG", "false").lower() == "true"


# ── 协议信息 ────────────────────────────────────────

@app.route("/api/info", methods=["GET"])
def api_info():
    """获取协议信息"""
    return jsonify(get_protocol_info())


@app.route("/api/channels", methods=["GET"])
def api_channels():
    """列出所有结算通道"""
    return jsonify(ChannelRegistry.list_all())


@app.route("/api/gates", methods=["GET"])
def api_gates():
    """列出所有验证门"""
    return jsonify(GateRegistry.list_all())


# ── Agent 管理 ──────────────────────────────────────

@app.route("/api/agents/register", methods=["POST"])
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


@app.route("/api/agents", methods=["GET"])
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


@app.route("/api/agents/<agent_id>", methods=["GET"])
def api_get_agent(agent_id):
    """获取 Agent 信息"""
    agent = AgentRegistry.get(agent_id)
    if agent:
        return jsonify(agent.to_dict())
    return jsonify({"error": f"未知 Agent: {agent_id}"}), 404


@app.route("/api/agents/<agent_id>/reputation", methods=["GET"])
def api_get_reputation(agent_id):
    """获取 Agent 信誉分"""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404

    rep = get_agent_reputation(agent_id, agent.wallet)
    return jsonify(rep)


@app.route("/api/agents/<agent_id>/reputation/update", methods=["POST"])
def api_update_reputation(agent_id):
    """更新 Agent 信誉分"""
    result = update_agent_reputation(agent_id)
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/agents/<agent_id>/records", methods=["GET"])
def api_get_records(agent_id):
    """获取 Agent 履约记录"""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404

    limit = int(request.args.get("limit", "100"))
    records = get_seller_records(agent.wallet, limit)
    return jsonify({"records": records})


# ── 任务执行 ────────────────────────────────────────

@app.route("/api/tasks/create", methods=["POST"])
def api_create_task():
    """创建任务"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = create_task(
        task_type=data.get("task_type", ""),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        amount=Decimal(str(data.get("amount", 0))),
        chain=data.get("chain", "bsc"),
        channel_id=data.get("channel_id"),
    )

    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@app.route("/api/tasks/verify", methods=["POST"])
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


@app.route("/api/tasks/complete", methods=["POST"])
def api_complete_task():
    """记录任务完成"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    status_str = data.get("status", "verified")
    status = TaskStatus(status_str) if status_str in [s.value for s in TaskStatus] else TaskStatus.VERIFIED

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


# ── Agent 自主下单 ──────────────────────────────────

@app.route("/api/agent-buy", methods=["POST"])
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


@app.route("/api/agents/best-match", methods=["GET"])
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

@app.route("/api/credit/issue", methods=["POST"])
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


@app.route("/api/credit", methods=["GET"])
def api_list_credit():
    """列出所有信用货币"""
    return jsonify({"currencies": list_credit_currencies()})


@app.route("/api/credit/<currency_id>/accept", methods=["POST"])
def api_accept_credit(currency_id):
    """接受信用货币"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "缺少请求体"}), 400

    result = accept_credit_currency(currency_id, data.get("agent_id", ""))
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


# ── 健康检查 ────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def health_check():
    """健康检查"""
    return jsonify({"status": "ok", "protocol": get_protocol_info()})


# ── 启动 ────────────────────────────────────────────

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 服务启动: http://localhost:{port}")
    print(f"协议信息: {json.dumps(get_protocol_info(), indent=2)}")

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    start_api()