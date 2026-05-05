"""
信用分 API — Flask 蓝图，可独立运行或挂载到主应用

独立运行: python -m credit_score.api
挂载: app.register_blueprint(credit_score_bp)
"""

import hashlib
import os
import time
import uuid

from flask import Blueprint, jsonify, request

from .calculator import SacredCalculator
from .bridge import CreditScoreBridge
from .store import CreditScoreStore
from .models import QueryAuthorization
from .config import DEFAULT_DB_PATH, AUTHORIZATION_TTL, AUTHORIZATION_MAX_TTL, API_HOST, API_PORT


credit_score_bp = Blueprint("credit_score", __name__, url_prefix="/api/v1/credit-score")

# 懒初始化
_calculator = None
_bridge = None
_store = None


def _ensure_initialized():
    global _calculator, _bridge, _store
    if _store is None:
        _store = CreditScoreStore(
            db_path=os.getenv("CREDIT_SCORE_DB_PATH", DEFAULT_DB_PATH)
        )
    if _calculator is None:
        _calculator = SacredCalculator()
    if _bridge is None:
        db_path = os.getenv("CRYPTOMINDS_DB_PATH", "cryptominds.db")
        _bridge = CreditScoreBridge(db_path=db_path)


def _get_internal_token():
    return os.getenv("CRYPTOMINDS_INTERNAL_TOKEN", "")


def _verify_internal_token():
    token = _get_internal_token()
    if not token:
        return True  # 无 token 配置时不验证
    req_token = request.headers.get("X-Internal-Token", "")
    return req_token == token


def _verify_agent_or_authorized(agent_id: str) -> bool:
    """验证请求者是 Agent 自身或持有有效授权"""
    # 1. Agent 自身（通过 internal token 或签名）
    if _verify_internal_token():
        return True

    # 2. 查询授权
    auth_id = request.headers.get("X-Auth-Id", "")
    querier_id = request.headers.get("X-Querier-Id", "")
    if auth_id and querier_id:
        return _store.verify_authorization(auth_id, querier_id)

    return False


# ── 端点 ──────────────────────────────────────────────


@credit_score_bp.route("/health", methods=["GET"])
def health():
    """健康检查"""
    _ensure_initialized()
    return jsonify({"status": "ok", "module": "credit_score", "version": "1.0.0"})


@credit_score_bp.route("/<agent_id>", methods=["GET"])
def get_score(agent_id: str):
    """查询信用分"""
    _ensure_initialized()

    # 排行榜公开，单个 Agent 分数需验证
    # 暂时允许查询，后续可加授权验证
    score = _store.get_latest_score(agent_id)
    if score is None:
        # 实时计算
        score = _calculate_for_agent(agent_id)
        if score is None:
            return jsonify({"error": "Agent not found"}), 404

    return jsonify(score.to_dict())


@credit_score_bp.route("/<agent_id>/profile", methods=["GET"])
def get_profile(agent_id: str):
    """信用画像 — 五维明细 + 历史 + 同行对比 + 风险提示"""
    _ensure_initialized()

    score = _store.get_latest_score(agent_id)
    if score is None:
        score = _calculate_for_agent(agent_id)
        if score is None:
            return jsonify({"error": "Agent not found"}), 404

    history = _store.get_score_history(agent_id, limit=10)

    # 同行对比
    stats = _store.get_score_statistics()
    peer_comparison = {}
    if stats.get("total_agents", 0) > 0:
        percentiles = stats.get("percentiles", {})
        # 该 Agent 超过了百分之多少的 Agent
        total = stats["total_agents"]
        # 简单估算：根据分数在百分位中的位置
        score_val = score.total_score
        beat_pct = 0
        for pname, pval in percentiles.items():
            if score_val >= pval:
                beat_pct = max(beat_pct, int(pname[1:]))
        if score_val >= stats.get("median_score", 0):
            beat_pct = max(beat_pct, 50)

        peer_comparison = {
            "total_agents": total,
            "beat_percent": beat_pct,
            "avg_score": stats.get("avg_score", 0),
            "median_score": stats.get("median_score", 0),
            "grade_distribution": stats.get("grade_counts", {}),
        }

    # 风险提示
    warnings = []
    for dim_code, dim in score.dimensions.items():
        ratio = dim.weighted_score / 200.0 if dim.weighted_score > 0 else 0
        if ratio < 0.3:
            warnings.append({
                "dimension": dim_code,
                "name": dim.name,
                "level": "high",
                "message": f"{dim.name}得分偏低，建议关注",
            })
        elif ratio < 0.5:
            warnings.append({
                "dimension": dim_code,
                "name": dim.name,
                "level": "medium",
                "message": f"{dim.name}得分一般，有提升空间",
            })

    # 趋势：最近3次分数变化
    trend = "stable"
    if len(history) >= 2:
        recent_scores = [h.score for h in history[:3]]
        if len(recent_scores) >= 2:
            diff = recent_scores[0] - recent_scores[-1]
            if diff > 20:
                trend = "rising"
            elif diff < -20:
                trend = "declining"

    return jsonify({
        **score.to_dict(),
        "history": [h.to_dict() for h in history],
        "peer_comparison": peer_comparison,
        "warnings": warnings,
        "trend": trend,
    })


@credit_score_bp.route("/<agent_id>/history", methods=["GET"])
def get_history(agent_id: str):
    """历史分数变化"""
    _ensure_initialized()

    limit = request.args.get("limit", 30, type=int)
    limit = min(limit, 100)

    history = _store.get_score_history(agent_id, limit=limit)
    return jsonify({
        "agent_id": agent_id,
        "history": [h.to_dict() for h in history],
    })


@credit_score_bp.route("/<agent_id>/authorize", methods=["POST"])
def create_authorization(agent_id: str):
    """Agent 签名授权第三方查询

    支持两种模式:
    1. 简单模式: 传 querier_id + signature（任意字符串）
    2. 链上模式: 传 querier_id + signature + message，服务端恢复签名者地址验证

    链上模式的消息格式: "authorize:{querier_id}:{timestamp}:{chain_id}"
    """
    _ensure_initialized()

    data = request.get_json(silent=True) or {}
    querier_id = data.get("querier_id", "")
    signature = data.get("signature", "")
    message = data.get("message", "")
    expires_in = data.get("expires_in", AUTHORIZATION_TTL)

    if not querier_id or not signature:
        return jsonify({"error": "querier_id and signature required"}), 400

    # 链上签名验证
    verified_wallet = None
    if message:
        try:
            verified_wallet = _verify_chain_signature(message, signature)
        except Exception as e:
            return jsonify({"error": f"Signature verification failed: {str(e)}"}), 400

    expires_in = min(expires_in, AUTHORIZATION_MAX_TTL)
    now = int(time.time())

    auth = QueryAuthorization(
        auth_id=hashlib.sha256(f"{agent_id}:{querier_id}:{now}".encode()).hexdigest()[:16],
        agent_id=agent_id,
        querier_id=querier_id,
        signature=signature,
        expires_at=now + expires_in,
        created_at=now,
    )

    _store.save_authorization(auth)

    result = {
        "auth_id": auth.auth_id,
        "agent_id": agent_id,
        "querier_id": querier_id,
        "expires_at": auth.expires_at,
    }
    if verified_wallet:
        result["verified_wallet"] = verified_wallet

    return jsonify(result), 201


@credit_score_bp.route("/<agent_id>/authorize/<auth_id>", methods=["DELETE"])
def revoke_authorization(agent_id: str, auth_id: str):
    """撤销授权"""
    _ensure_initialized()

    success = _store.revoke_authorization(auth_id)
    if success:
        return jsonify({"status": "revoked", "auth_id": auth_id})
    return jsonify({"error": "Authorization not found"}), 404


@credit_score_bp.route("/<agent_id>/refresh", methods=["POST"])
def refresh_score(agent_id: str):
    """触发重新计算"""
    _ensure_initialized()

    if not _verify_internal_token():
        return jsonify({"error": "Unauthorized"}), 403

    score = _calculate_for_agent(agent_id)
    if score is None:
        return jsonify({"error": "Agent not found"}), 404

    return jsonify(score.to_dict())


@credit_score_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """排行榜"""
    _ensure_initialized()

    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 200)
    grade = request.args.get("grade", None)

    lb = _store.get_leaderboard(limit=limit, grade=grade)
    return jsonify({"leaderboard": lb})


# ── 内部方法 ──────────────────────────────────────────


def _verify_chain_signature(message: str, signature: str) -> str:
    """验证链上签名，返回恢复的钱包地址

    使用 eth_account 的 personal_ec_recover 从签名恢复地址。
    消息格式: "authorize:{querier_id}:{timestamp}:{chain_id}"
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        # EIP-191 个人签名恢复
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=signature)
        return recovered
    except ImportError:
        raise ValueError("eth_account not installed, chain signature verification unavailable")
    except Exception as e:
        raise ValueError(f"Signature recovery failed: {str(e)}")


def _calculate_for_agent(agent_id: str):
    """实时计算 Agent 信用分"""
    try:
        wallet = _bridge.get_agent_wallet(agent_id)
    except Exception:
        return None

    if wallet is None:
        return None

    # 获取履约记录
    record_dicts = _bridge.get_records_by_seller(wallet)
    records = _bridge.records_to_performance_records(record_dicts)

    # 获取信用数据
    credit_acceptance = _bridge.get_credit_acceptance(agent_id)
    accepted_by_agent = _bridge.get_accepted_by_agent(agent_id)
    currencies = _bridge.get_credit_currencies()

    credit_data = {
        "accepted_count": credit_acceptance.get("accepted_count", 0),
        "accepted_by_agent": accepted_by_agent,
        "currencies": currencies,
    }

    # 获取 Agent 信息
    chains = _bridge.get_chain_coverage(wallet)
    counterparts = _bridge.get_unique_counterparts(wallet)
    escrow_orders = _bridge.get_escrow_orders_by_seller(wallet)
    total_escrow = sum(float(o.get("amount", 0)) for o in escrow_orders)

    agent_info = {
        "staked": total_escrow,  # 用托管量近似
        "active_chains": chains,
        "counterparts": counterparts,
    }

    score = _calculator.calculate(
        agent_id=agent_id,
        wallet=wallet,
        records=records,
        credit_data=credit_data,
        agent_info=agent_info,
    )

    _store.save_score(score)
    return score


# ── 独立运行入口 ──────────────────────────────────────


def start_standalone(host: str = None, port: int = None):
    """独立运行信用分 API 服务"""
    from flask import Flask, send_from_directory

    app = Flask(__name__,
                static_folder=os.path.join(os.path.dirname(__file__), "dashboard"),
                static_url_path="/dashboard")
    app.register_blueprint(credit_score_bp)

    @app.route("/")
    def index():
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), "dashboard"),
            "index.html",
        )

    host = host or API_HOST
    port = port or API_PORT

    print(f"[credit_score] Starting API on {host}:{port}")
    print(f"[credit_score] Dashboard: http://{host}:{port}/")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    start_standalone()
