"""
CryptoMinds 信用层 API 服务

AI Agent 信用分基础设施
- SACRED五维信用分查询
- 履约记录上报
- 信任网络分析
"""

import os
import sys
import hashlib

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, g  # noqa: E402
from flask_limiter import Limiter  # noqa: E402
from flask_limiter.util import get_remote_address  # noqa: E402

from credit.api import credit_bp  # noqa: E402
from store import UnifiedStore  # noqa: E402

# 创建 Flask 应用
app = Flask(__name__)

# 速率限制
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# 配置
DEBUG_MODE = os.getenv("CRYPTOMINDS_DEBUG", "false").lower() in ("1", "true", "yes")
API_PORT = int(os.getenv("CRYPTOMINDS_API_PORT", "3458"))

# API 认证配置
API_KEY = os.getenv("CRYPTOMINDS_API_KEY", "")
INTERNAL_TOKEN = os.getenv("CRYPTOMINDS_INTERNAL_TOKEN", "")
REQUIRE_AUTH = os.getenv("CRYPTOMINDS_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes")

# 初始化统一存储
store = UnifiedStore()


# ── 认证中间件 ──

def check_auth():
    """检查 API 认证"""
    if not REQUIRE_AUTH:
        return None

    # 优先检查内部令牌（交易层调用）
    internal_token = request.headers.get("X-CryptoMinds-Internal-Token")
    if internal_token and INTERNAL_TOKEN:
        expected = hashlib.sha256(INTERNAL_TOKEN.encode()).hexdigest()
        provided = hashlib.sha256(internal_token.encode()).hexdigest()
        if provided == expected:
            g.auth_type = "internal"
            return None

    # 检查 API Key
    api_key = request.headers.get("X-CryptoMinds-API-Key")
    if api_key and API_KEY:
        expected = hashlib.sha256(API_KEY.encode()).hexdigest()
        provided = hashlib.sha256(api_key.encode()).hexdigest()
        if provided == expected:
            g.auth_type = "api_key"
            return None

    return jsonify({"error": "未授权访问"}), 401


@app.before_request
def before_request():
    """请求前中间件"""
    if request.path in ("/health", "/api/v1/info"):
        return None
    return check_auth()


# ── 健康检查 ──

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "cryptominds-credit"})


@app.route("/api/v1/info")
def info():
    return jsonify({
        "name": "CryptoMinds Credit Layer",
        "version": "1.0.0",
        "description": "AI Agent 信用分基础设施",
        "features": ["sacred_credit", "trust_network", "performance_records"]
    })


# ── 信用分 API ──

app.register_blueprint(credit_bp, url_prefix="/api/v1/credit")


# ── 履约记录上报 API（供交易层调用）──

@app.route("/api/v1/records", methods=["POST"])
def create_record():
    """
    上报履约记录

    交易层调用此接口上报任务完成情况，用于更新信用分
    """
    data = request.json
    required = ["record_id", "seller_agent_id", "success"]
    if not all(k in data for k in required):
        return jsonify({"error": "缺少必要参数"}), 400

    from credit.models import PerformanceRecord, TaskStatus

    record = PerformanceRecord(
        record_id=data["record_id"],
        task_id=data.get("task_id", data["record_id"]),
        task_type=data.get("task_type", "token_delivery"),
        buyer_wallet=data.get("buyer_wallet", ""),
        seller_wallet=data.get("seller_wallet", ""),
        seller_agent_id=data["seller_agent_id"],
        chain=data.get("chain", "bsc"),
        amount=data.get("amount", "0"),
        status=TaskStatus.SETTLED if data["success"] else TaskStatus.REFUNDED,
        success=data["success"],
        score=data.get("score", 0.5),
        created_at=data.get("created_at", 0),
        completed_at=data.get("completed_at", 0),
        response_time_ms=data.get("response_time_ms", 0),
        payment_tx=data.get("payment_tx", ""),
        payment_amount=data.get("payment_amount", "0"),
        evidence=data.get("evidence", ""),
        disputed=data.get("disputed", False),
        dispute_reason=data.get("dispute_reason", ""),
        resolution=data.get("resolution", ""),
    )

    store.save_performance_record(record)

    # 触发信用分重新计算
    from credit.calculator import SacredCalculator
    calculator = SacredCalculator()
    records = store.get_performance_records(agent_id=data["seller_agent_id"])
    score = calculator.calculate(
        agent_id=data["seller_agent_id"],
        wallet=data.get("seller_wallet", data["seller_agent_id"]),
        records=records,
    )
    store.save_score(score)

    return jsonify({
        "ok": True,
        "record_id": record.record_id,
        "credit_score": score.total_score,
        "credit_grade": score.grade,
    })


# ── 信用分应用预览 API ──

@app.route("/api/v1/preview/deposit-discount", methods=["POST"])
def preview_deposit_discount():
    """预览押金折扣"""
    data = request.json or {}
    agent_id = data.get("agent_id")
    amount = float(data.get("amount", 1.0))

    if not agent_id:
        return jsonify({"error": "缺少 Agent ID"}), 400

    score_data = store.get_latest_score(agent_id)

    if not score_data:
        return jsonify({
            "agent_id": agent_id,
            "credit_score": 0,
            "credit_grade": "N/A",
            "discount_percent": "0%",
            "required_deposit": amount,
        })

    if hasattr(score_data, "total_score"):
        score = score_data.total_score
        grade = score_data.grade
    else:
        score = score_data.get("total_score", 0)
        grade = score_data.get("grade", "C")

    # 根据等级计算折扣
    discounts = {
        "AAA": 0.30, "AA": 0.20, "A": 0.10,
        "BBB": 0.05, "BB": 0.00, "B": 0.00
    }
    discount_rate = discounts.get(grade, 0)

    return jsonify({
        "agent_id": agent_id,
        "credit_score": score,
        "credit_grade": grade,
        "discount_percent": f"{int(discount_rate * 100)}%",
        "required_deposit": round(amount * (1 - discount_rate), 4),
        "original_deposit": amount,
        "savings": round(amount * discount_rate, 4),
    })


@app.route("/api/v1/preview/voucher-limit", methods=["POST"])
def preview_voucher_limit():
    """预览Voucher额度上限"""
    data = request.json or {}
    agent_id = data.get("agent_id")

    if not agent_id:
        return jsonify({"error": "缺少 Agent ID"}), 400

    score_data = store.get_latest_score(agent_id)

    if not score_data:
        return jsonify({
            "agent_id": agent_id,
            "credit_score": 0,
            "credit_grade": "N/A",
            "multiplier": "1x",
            "max_limit": 100,
        })

    if hasattr(score_data, "total_score"):
        score = score_data.total_score
        grade = score_data.grade
    else:
        score = score_data.get("total_score", 0)
        grade = score_data.get("grade", "C")

    multipliers = {
        "AAA": 5, "AA": 3, "A": 2, "BBB": 1.5,
        "BB": 1.2, "B": 1.1
    }
    multiplier = multipliers.get(grade, 1)

    return jsonify({
        "agent_id": agent_id,
        "credit_score": score,
        "credit_grade": grade,
        "multiplier": f"{multiplier}x",
        "max_limit": 100 * multiplier,
        "base_limit": 100,
    })


@app.route("/api/v1/preview/arbitration-weight", methods=["POST"])
def preview_arbitration_weight():
    """预览仲裁权重"""
    data = request.json or {}
    agent_id = data.get("agent_id")

    if not agent_id:
        return jsonify({"error": "缺少 Agent ID"}), 400

    score_data = store.get_latest_score(agent_id)

    if not score_data:
        return jsonify({
            "agent_id": agent_id,
            "credit_score": 0,
            "credit_grade": "N/A",
            "weight_multiplier": 1.0,
            "effective_weight": 1.0,
        })

    if hasattr(score_data, "total_score"):
        score = score_data.total_score
        grade = score_data.grade
    else:
        score = score_data.get("total_score", 0)
        grade = score_data.get("grade", "C")

    # 仲裁权重 = 1 + (信用分 / 1000) * 0.7
    weight_multiplier = 1.0 + (score / 1000) * 0.7

    return jsonify({
        "agent_id": agent_id,
        "credit_score": score,
        "credit_grade": grade,
        "weight_multiplier": round(weight_multiplier, 2),
        "base_weight": 1.0,
        "effective_weight": round(weight_multiplier, 2),
    })


# ── 信任网络 API ──

@app.route("/api/v1/trust-network", methods=["GET"])
def trust_network():
    """获取信任网络数据"""
    limit = request.args.get("limit", 500, type=int)
    limit = min(limit, 2000)

    network = store.get_trust_network(limit=limit)
    return jsonify(network)


@app.route("/api/v1/trust-path/<from_agent>/<to_agent>", methods=["GET"])
def trust_path(from_agent: str, to_agent: str):
    """查询两个Agent之间的信任路径"""
    max_depth = request.args.get("max_depth", 4, type=int)
    max_depth = min(max_depth, 6)

    path = store.find_trust_path(from_agent, to_agent, max_depth=max_depth)

    return jsonify({
        "from": from_agent,
        "to": to_agent,
        "path": path,
        "found": len(path) > 0,
    })


@app.route("/api/v1/trust-score/<agent_id>", methods=["GET"])
def trust_score(agent_id: str):
    """获取Agent的综合信任评分"""
    from_agent = request.args.get("from")

    result = store.get_agent_trust_score(
        agent_id=agent_id,
        from_agent=from_agent,
    )

    return jsonify(result)


# ── 启动 ──

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds 信用层 API 启动: http://localhost:{port}")
    print(f"Debug 模式: {debug}")

    if not debug:
        try:
            from gunicorn.app.base import BaseApplication  # noqa: E402

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
                "bind": f"0.0.0.0:{port}",
                "workers": int(os.getenv("GUNICORN_WORKERS", "2")),
                "threads": int(os.getenv("GUNICORN_THREADS", "4")),
                "timeout": 120,
                "accesslog": "-",
                "errorlog": "-",
            }
            print(f"[production] gunicorn 启动: {options['bind']}")
            StandaloneApplication(app, options).run()
            return
        except ImportError:
            print("[warning] gunicorn 未安装，使用 Flask 开发服务器")

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    start_api()
