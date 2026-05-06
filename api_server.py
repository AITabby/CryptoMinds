# flake8: noqa
"""
CryptoMinds API 服务层

将协议暴露为 HTTP API，供 Agent 调用。
模块化版本 — 所有路由在 api/blueprints/ 下，共享逻辑在 api/ 下。
"""

import hmac
import json
import os
import sys

import api as _api_module
import api.auth as _auth_module
import api.stores as _store_module
from api import create_app, API_PORT, DEBUG_MODE
from api.blueprints.market import MARKET_TASKS

app = create_app()

from protocol import get_protocol_info


# Back-compat facade for tests and integrations that imported helpers from the
# pre-modular api_server.py. The implementation lives in api/*.
_env_config = _api_module._env_config
INTERNAL_TOKEN = _api_module.INTERNAL_TOKEN
_db_path = _store_module._db_path
_stores_cache = _store_module._stores_cache


def _sync_store_compat_state():
    """Keep api_server facade store knobs synchronized with api.stores."""
    global _stores_cache
    if _store_module._db_path != _db_path:
        _store_module._db_path = _db_path
        _store_module._stores_cache = _stores_cache
    else:
        _stores_cache = _store_module._stores_cache


@app.before_request
def _api_server_compat_before_request():
    _sync_store_compat_state()


def _get_escrow_store():
    _sync_store_compat_state()
    store = _store_module._get_escrow_store()
    _sync_store_compat_state()
    return store


def _get_record_store():
    _sync_store_compat_state()
    store = _store_module._get_record_store()
    _sync_store_compat_state()
    return store


def _get_voucher_store():
    _sync_store_compat_state()
    store = _store_module._get_voucher_store()
    _sync_store_compat_state()
    return store


def _get_session_key_store():
    _sync_store_compat_state()
    store = _store_module._get_session_key_store()
    _sync_store_compat_state()
    return store


def _write_audit_log(*args, **kwargs):
    return _store_module._write_audit_log(*args, **kwargs)


def _is_demo_mode() -> bool:
    return bool(_env_config.get("DEMO_MODE")) or os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")


def _is_protected_env() -> bool:
    env_name = (_env_config.get("env") or os.getenv("CRYPTOMINDS_ENV", "dev")).lower()
    if DEBUG_MODE or os.getenv("CRYPTOMINDS_DEBUG", "false").lower() in ("1", "true", "yes"):
        return False
    return env_name in ("staging", "prod") or not _is_demo_mode()


def _reject_demo_private_key(main_private_key: str):
    if not main_private_key or main_private_key.upper() in ("DEMO", "PLACEHOLDER", "TEST"):
        if _is_protected_env():
            from flask import jsonify
            return jsonify({"error": "生产/测试网环境不允许使用 DEMO 私钥占位符，请使用钱包签名授权"}), 400
    return None


def require_internal_token():
    supplied = _auth_module.request.headers.get("X-CryptoMinds-Internal-Token", "")
    token = _env_config.get("INTERNAL_TOKEN") or os.getenv("CRYPTOMINDS_INTERNAL_TOKEN", "")
    if not token:
        return not _is_protected_env()
    return len(supplied) == len(token) and hmac.compare_digest(supplied, token)


def start_api(port=None, debug=None):
    """启动 API 服务"""
    app = create_app()
    port = port or API_PORT
    debug = debug if debug is not None else DEBUG_MODE

    print(f"CryptoMinds API 服务启动: http://localhost:{port}")
    print(f"协议信息: {json.dumps(get_protocol_info(), indent=2)}")

    # Start SQLite backup thread
    db_path = os.getenv("CRYPTOMINDS_DB_PATH", str(os.path.join(os.path.dirname(__file__), "web", "cryptominds.db")))
    from data.sqlite_store import start_backup_thread, register_shutdown_checkpoint
    start_backup_thread(db_path)
    register_shutdown_checkpoint(db_path)

    # Start Escrow Watchdog
    from api.stores import _get_escrow_store, _get_record_store
    from protocol import AgentRegistry
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
