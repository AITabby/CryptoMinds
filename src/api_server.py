"""
CryptoMinds API 服务

AI Agent 信任基础设施 API
- 信用分查询
- 托管管理
- 争议仲裁
"""

import os
import sys

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 导入核心模块
from credit.api import credit_bp
from escrow.store import EscrowStore
from escrow.arbitration_store import ArbitrationStore

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

# 初始化存储
escrow_store = EscrowStore()
arbitration_store = ArbitrationStore()


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

    escrow = escrow_store.create(
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
    escrow = escrow_store.get(escrow_id)
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

    escrow = escrow_store.fund(escrow_id, tx_hash)
    if not escrow:
        return jsonify({"error": "托管不存在或状态不允许"}), 400
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/deliver", methods=["POST"])
def escrow_deliver(escrow_id):
    """提交交付证明"""
    data = request.json
    proof = data.get("proof")
    if not proof:
        return jsonify({"error": "缺少交付证明"}), 400

    escrow = escrow_store.deliver(escrow_id, proof)
    if not escrow:
        return jsonify({"error": "托管不存在或状态不允许"}), 400
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/release", methods=["POST"])
def escrow_release(escrow_id):
    """释放资金"""
    escrow = escrow_store.release(escrow_id)
    if not escrow:
        return jsonify({"error": "托管不存在或状态不允许"}), 400
    return jsonify(escrow)


@app.route("/api/v1/escrow/<escrow_id>/refund", methods=["POST"])
def escrow_refund(escrow_id):
    """申请退款"""
    escrow = escrow_store.refund(escrow_id)
    if not escrow:
        return jsonify({"error": "托管不存在或状态不允许"}), 400
    return jsonify(escrow)


# ── 仲裁 API ──

@app.route("/api/v1/arbitrate/submit", methods=["POST"])
def arbitrate_submit():
    """提交争议"""
    data = request.json
    required = ["escrow_id", "reason"]
    if not all(k in data for k in required):
        return jsonify({"error": "缺少必要参数"}), 400

    dispute = arbitration_store.create(
        escrow_id=data["escrow_id"],
        reason=data["reason"],
        evidence=data.get("evidence")
    )
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>", methods=["GET"])
def arbitrate_get(dispute_id):
    """查询争议状态"""
    dispute = arbitration_store.get(dispute_id)
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>/evidence", methods=["POST"])
def arbitrate_evidence(dispute_id):
    """添加证据"""
    data = request.json
    dispute = arbitration_store.add_evidence(dispute_id, data)
    if not dispute:
        return jsonify({"error": "争议不存在"}), 404
    return jsonify(dispute)


@app.route("/api/v1/arbitrate/<dispute_id>/arbitrators", methods=["GET"])
def arbitrate_arbitrators(dispute_id):
    """查询仲裁员"""
    arbitrators = arbitration_store.get_arbitrators(dispute_id)
    return jsonify({"arbitrators": arbitrators})


# ── 启动 ──

def start_api(port=None, debug=None):
    """启动 API 服务"""
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 启动: http://localhost:{port}")
    print(f"Debug 模式: {debug}")

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
