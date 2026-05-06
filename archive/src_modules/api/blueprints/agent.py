# flake8: noqa
"""
CryptoMinds API — Agent management blueprint (6 routes)
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify

from protocol import register_agent, search_agents, find_best_agent, get_agent_reputation, update_agent_reputation, get_seller_records, AgentRegistry
from agent.capability import AgentCapability, CapabilitySpec, ReputationInfo
from api.auth import require_auth
from api import _increment_metric

agent_bp = Blueprint("agent", __name__, url_prefix="/api/v1")


@agent_bp.route("/agents/register", methods=["POST"])
@require_auth
def api_register_agent():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少请求体"}), 400

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


@agent_bp.route("/agents", methods=["GET"])
def api_list_agents():
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


@agent_bp.route("/agents/<agent_id>", methods=["GET"])
def api_get_agent(agent_id):
    agent = AgentRegistry.get(agent_id)
    if agent:
        return jsonify(agent.to_dict())
    return jsonify({"error": f"未知 Agent: {agent_id}"}), 404


@agent_bp.route("/agents/<agent_id>/reputation", methods=["GET"])
def api_get_reputation(agent_id):
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404
    rep = get_agent_reputation(agent_id, agent.wallet)
    return jsonify(rep)


@agent_bp.route("/agents/<agent_id>/reputation/update", methods=["POST"])
@require_auth
def api_update_reputation(agent_id):
    result = update_agent_reputation(agent_id)
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


@agent_bp.route("/agents/<agent_id>/records", methods=["GET"])
def api_get_records(agent_id):
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return jsonify({"error": f"未知 Agent: {agent_id}"}), 404
    limit = int(request.args.get("limit", "100"))
    records = get_seller_records(agent.wallet, limit)
    return jsonify({"records": records})
