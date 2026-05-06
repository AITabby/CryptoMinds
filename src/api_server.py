"""
CryptoMinds API 服务

AI Agent 信任基础设施 API
- 信用分查询
- 托管管理
- 争议仲裁
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

    # 优先检查内部令牌
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

    # 检查签名（Agent 钱包签名）
    signature = request.headers.get("X-CryptoMinds-Signature")
    address = request.headers.get("X-CryptoMinds-Address")
    timestamp = request.headers.get("X-CryptoMinds-Timestamp")

    if signature and address and timestamp:
        try:
            timestamp_int = int(timestamp)
        except ValueError:
            return jsonify({"error": "无效的时间戳"}), 401

        # 确定操作类型
        action = request.path.replace("/api/v1/", "").replace("/", "_")

        # 验证签名
        from utils.signature import verify_api_signature
        result = verify_api_signature(
            signature=signature,
            address=address,
            action=action,
            timestamp=timestamp_int,
        )

        if result.get("valid"):
            g.auth_type = "signature"
            g.signer_address = result.get("recovered_address", address)
            return None
        else:
            return jsonify({"error": result.get("error", "签名验证失败")}), 401

    return jsonify({"error": "未授权访问，请提供有效的认证信息"}), 401


@app.before_request
def before_request():
    """请求前中间件"""
    # 跳过健康检查
    if request.path in ("/health", "/api/v1/info"):
        return None

    # 检查认证
    return check_auth()


# ── 健康检查 ──

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "cryptominds-api"})


@app.route("/api/v1/info")
def info():
    return jsonify({
        "name": "CryptoMinds",
        "version": "0.1.0",
        "description": "AI Agent 信任基础设施",
        "features": ["credit", "escrow", "arbitration"]
    })


# ── 信用分 API ──

app.register_blueprint(credit_bp, url_prefix="/api/v1/credit")


# ── 托管 API ──

@app.route("/api/v1/escrow/create", methods=["POST"])
def escrow_create():
    """创建托管"""
    data = request.json
    required = ["buyer", "seller", "amount"]
    if not all(k in data for k in required):
        return jsonify({"error": "缺少必要参数"}), 400

    escrow = store.create_escrow(
        buyer=data["buyer"],
        seller=data["seller"],
        amount=float(data["amount"]),
        token=data.get("token", "BNB"),
        timeout=data.get("timeout", 86400),
        metadata=data.get("metadata")
    )
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>", methods=["GET"])
def escrow_get(escrow_id):
    """查询托管状态"""
    escrow = store.get_escrow(escrow_id)
    if not escrow:
        return jsonify({"error": "托管不存在"}), 404
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/fund", methods=["POST"])
def escrow_fund(escrow_id):
    """确认资金托管"""
    data = request.json
    tx_hash = data.get("tx_hash")
    if not tx_hash:
        return jsonify({"error": "缺少交易哈希"}), 400

    escrow = store.get_escrow(escrow_id)
    if not escrow or escrow["status"] != "pending":
        return jsonify({"error": "托管不存在或状态不允许"}), 400

    escrow = store.update_escrow_status(
        escrow_id, "funded",
        fund_tx=tx_hash,
        funded_at=int(__import__("time").time()),
    )
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/deliver", methods=["POST"])
def escrow_deliver(escrow_id):
    """提交交付证明"""
    data = request.json
    proof = data.get("proof")
    if not proof:
        return jsonify({"error": "缺少交付证明"}), 400

    escrow = store.get_escrow(escrow_id)
    if not escrow or escrow["status"] != "funded":
        return jsonify({"error": "托管不存在或状态不允许"}), 400

    escrow = store.update_escrow_status(
        escrow_id, "delivered",
        delivery_proof=str(proof),
        delivered_at=int(__import__("time").time()),
    )
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/release", methods=["POST"])
def escrow_release(escrow_id):
    """释放资金"""
    escrow = store.get_escrow(escrow_id)
    if not escrow or escrow["status"] not in ("delivered", "verified"):
        return jsonify({"error": "托管不存在或状态不允许"}), 400

    escrow = store.update_escrow_status(
        escrow_id, "settled",
        completed_at=int(__import__("time").time()),
    )

    # 写入履约记录
    _record_escrow_result(escrow_id, "settled")

    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/refund", methods=["POST"])
def escrow_refund(escrow_id):
    """申请退款"""
    escrow = store.get_escrow(escrow_id)
    if not escrow:
        return jsonify({"error": "托管不存在"}), 404

    allowed = ("pending", "funded", "disputed", "arbitrating")
    if escrow["status"] not in allowed:
        return jsonify({"error": "状态不允许退款"}), 400

    escrow = store.update_escrow_status(
        escrow_id, "refunded",
        completed_at=int(__import__("time").time()),
    )

    # 写入履约记录
    _record_escrow_result(escrow_id, "refunded")

    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/dispute", methods=["POST"])
def escrow_dispute(escrow_id):
    """发起争议"""
    data = request.json
    reason = data.get("reason", "")

    escrow = store.get_escrow(escrow_id)
    if not escrow or escrow["status"] not in ("delivered", "funded"):
        return jsonify({"error": "托管不存在或状态不允许"}), 400

    escrow = store.update_escrow_status(
        escrow_id, "disputed",
        disputed=True,
        dispute_reason=reason,
    )

    # 创建争议记录
    dispute = store.create_dispute(
        escrow_id=escrow_id,
        reason=reason,
        evidence=data.get("evidence"),
    )
    return jsonify({"escrow": escrow, "dispute": dispute})


# ── 仲裁 API ──

@app.route("/api/v1/arbitrate/submit", methods=["POST"])
def arbitrate_submit():
    """提交争议"""
    data = request.json
    required = ["escrow_id", "reason"]
    if not all(k in data for k in required):
        return jsonify({"error": "缺少必要参数"}), 400

    dispute = store.create_dispute(
        escrow_id=data["escrow_id"],
        reason=data["reason"],
        evidence=data.get("evidence")
    )
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>", methods=["GET"])
def arbitrate_get(dispute_id):
    """查询争议状态"""
    dispute = store.get_dispute(dispute_id)
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>/evidence", methods=["POST"])
def arbitrate_evidence(dispute_id):
    """添加证据"""
    data = request.json
    dispute = store.add_dispute_evidence(dispute_id, data)
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>/arbitrators", methods=["GET"])
def arbitrate_arbitrators(dispute_id):
    """查询仲裁员"""
    dispute = store.get_dispute(dispute_id)
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify({"arbitrators": dispute.get("arbitrators", [])})


@app.route("/api/v1/arbitrate/<dispute_id>/vote", methods=["POST"])
def arbitrate_vote(dispute_id):
    """仲裁员投票"""
    data = request.json
    required = ["arbitrator", "vote", "weight"]
    if not all(k in data for k in required):
        return jsonify({"error": "缺少必要参数"}), 400

    dispute = store.add_vote(
        dispute_id=dispute_id,
        arbitrator=data["arbitrator"],
        vote=data["vote"],
        weight=float(data["weight"]),
    )
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>/resolve", methods=["POST"])
def arbitrate_resolve(dispute_id):
    """解决争议"""
    data = request.json
    result = data.get("result")
    if not result:
        return jsonify({"error": "缺少结果参数"}), 400

    dispute = store.resolve_dispute(
        dispute_id=dispute_id,
        result=result,
        reason=data.get("reason", ""),
    )
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404

    # 更新托管状态 + 写履约记录
    escrow_id = dispute["escrow_id"]
    now = int(__import__("time").time())
    if result == "buyer_wins":
        store.update_escrow_status(
            escrow_id, "refunded",
            resolution="buyer_win", completed_at=now)
        _record_escrow_result(escrow_id, "refunded")
    elif result == "seller_wins":
        store.update_escrow_status(
            escrow_id, "settled",
            resolution="seller_win", completed_at=now)
        _record_escrow_result(escrow_id, "settled")

    return jsonify(dispute)


# ── 辅助函数 ──

def _record_escrow_result(escrow_id: str, result: str):
    """托管结算后自动写入履约记录"""
    from credit.models import PerformanceRecord, TaskStatus

    escrow = store.get_escrow(escrow_id)
    if not escrow:
        return

    status_map = {
        "settled": TaskStatus.SETTLED,
        "refunded": TaskStatus.REFUNDED,
    }
    task_status = status_map.get(result, TaskStatus.SETTLED)

    response_time = 0
    if escrow.get("delivered_at") and escrow.get("created_at"):
        response_time = (escrow["delivered_at"] - escrow["created_at"]) * 1000

    record = PerformanceRecord(
        record_id=f"perf_{escrow_id}",
        task_id=escrow_id,
        task_type="escrow",
        buyer_wallet=escrow["buyer"],
        seller_wallet=escrow["seller"],
        seller_agent_id=escrow["seller"],
        chain="bsc",
        amount=str(escrow["amount"]),
        status=task_status,
        success=task_status == TaskStatus.SETTLED,
        score=0.5,  # 默认中性分数
        created_at=escrow["created_at"],
        completed_at=escrow.get("completed_at", 0),
        response_time_ms=response_time,
        payment_tx=escrow.get("fund_tx", ""),
        payment_amount=escrow.get("amount", "0"),
        evidence=escrow.get("evidence", ""),
        disputed=escrow.get("disputed", False),
        dispute_reason=escrow.get("dispute_reason", ""),
        resolution=escrow.get("resolution", ""),
    )

    store.save_performance_record(record)


# ── 启动 ──

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 启动: http://localhost:{port}")
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
