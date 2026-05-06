# flake8: noqa
"""
CryptoMinds API — Flask application factory
"""

import json
import logging
import os
import time

from flask import Flask, request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from logging_config import setup_logging, generate_request_id
setup_logging()
logger = logging.getLogger(__name__)

from scripts.env_loader import load_env
_env_config = load_env()

# Sentry
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

# Config
API_PORT = _env_config["API_PORT"]
DEBUG_MODE = _env_config["DEBUG"]
INTERNAL_TOKEN = _env_config["INTERNAL_TOKEN"]

# ── Prometheus metrics ────────────────────────────────────

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

METRIC_AGENTS_ONLINE = Gauge("cryptominds_python_agents_online", "Agents currently online")
METRIC_MARKET_TASKS = Gauge("cryptominds_python_market_tasks", "Tasks in the market")

METRIC_HTTP_REQUESTS = Counter(
    "cryptominds_python_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
METRIC_HTTP_DURATION = Histogram(
    "cryptominds_python_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

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


# ── App factory ────────────────────────────────────────────

def create_app():
    app = Flask(__name__)

    # Rate limiter
    RATE_LIMIT_PER_MINUTE = os.getenv("RATE_LIMIT_PER_MINUTE", "60")
    _is_debug = os.getenv("CRYPTOMINDS_DEBUG", "false").lower() == "true"
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[] if _is_debug else [f"{RATE_LIMIT_PER_MINUTE} per minute"],
        storage_uri="memory://",
    )
    app.extensions["limiter"] = limiter

    # Middleware
    @app.before_request
    def log_request_start():
        g._start_time = time.time()

    @app.before_request
    def redirect_old_api():
        if request.path.startswith("/api/") and not request.path.startswith("/api/v1/"):
            from flask import redirect
            return redirect(f"/api/v1{request.path[4:]}", code=301)
        g._request_id = request.headers.get("X-Request-ID") or generate_request_id()
        g._start_time = time.time()

    @app.after_request
    def add_cors_and_log(response):
        allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
        origin = request.headers.get("Origin", "")
        if allowed_origins == "*":
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in allowed_origins.split(","):
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-402-Payment, X-Request-ID"
        request_id = g.get("_request_id", "")
        if request_id:
            response.headers["X-Request-ID"] = request_id
        if request.method == "OPTIONS":
            response.status_code = 204

        duration_ms = (time.time() - g.get('_start_time', time.time())) * 1000
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

    # Register blueprints
    from api.blueprints.protocol import protocol_bp
    from api.blueprints.agent import agent_bp
    from api.blueprints.task import task_bp
    from api.blueprints.market import market_bp
    from api.blueprints.credit import credit_bp
    from api.blueprints.escrow import escrow_bp
    from api.blueprints.voucher import voucher_bp
    from api.blueprints.session_key import session_key_bp
    from api.blueprints.health import health_bp

    app.register_blueprint(protocol_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(credit_bp)
    app.register_blueprint(escrow_bp)
    app.register_blueprint(voucher_bp)
    app.register_blueprint(session_key_bp)
    app.register_blueprint(health_bp)

    return app
