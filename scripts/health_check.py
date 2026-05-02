"""
CryptoMinds 健康检查脚本
检查各组件状态，返回 JSON 格式结果
"""
import json
import sys
import os
import socket
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def check_port(host, port, timeout=3):
    """检查端口是否可达"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_health():
    results = {
        "timestamp": int(time.time()),
        "status": "healthy",
        "checks": {}
    }

    # 检查 wallets.json
    wallets_ok = (PROJECT_ROOT / 'wallets.json').exists()
    results["checks"]["wallets"] = {
        "status": "ok" if wallets_ok else "error",
        "detail": "wallets.json 存在" if wallets_ok else "wallets.json 缺失"
    }

    # 检查 Web Dashboard
    web_ok = check_port('127.0.0.1', 3457)
    results["checks"]["web_dashboard"] = {
        "status": "ok" if web_ok else "down",
        "port": 3457,
        "detail": "http://localhost:3457" if web_ok else "未运行"
    }

    # 检查 Python API
    api_port = int(os.getenv("API_PORT", "3458"))
    api_ok = check_port('127.0.0.1', api_port)
    results["checks"]["python_api"] = {
        "status": "ok" if api_ok else "down",
        "port": api_port,
        "detail": f"http://localhost:{api_port}" if api_ok else "未运行"
    }

    # 检查 BSC RPC 连通性
    try:
        import requests
        rpc_url = os.getenv('BSC_RPC', 'https://bsc-dataseed1.binance.org/')
        resp = requests.post(rpc_url, json={
            "jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1
        }, timeout=5)
        rpc_ok = resp.status_code == 200
        block = int(resp.json().get('result', '0x0'), 16) if rpc_ok else 0
    except Exception:
        rpc_ok = False
        block = 0

    results["checks"]["bsc_rpc"] = {
        "status": "ok" if rpc_ok else "error",
        "detail": f"区块高度: {block}" if rpc_ok else "RPC 不可达"
    }

    # 检查 Agent Registry (via API)
    if api_ok:
        try:
            import requests as _req
            token = os.getenv("INTERNAL_TOKEN", "")
            headers = {"Authorization": f"Bearer {token}", "X-CryptoMinds-Internal-Token": token}
            r = _req.get(f"http://127.0.0.1:{api_port}/api/v1/agents", headers=headers, timeout=5)
            if r.status_code == 200:
                agents_data = r.json()
                total = len(agents_data.get("agents", []))
                online = sum(1 for a in agents_data.get("agents", []) if a.get("online", False))
                results["checks"]["agent_registry"] = {
                    "status": "ok" if total > 0 else "warning",
                    "detail": f"{online}/{total} agents online",
                    "total": total,
                    "online": online,
                }
            else:
                results["checks"]["agent_registry"] = {"status": "error", "detail": f"API 返回 {r.status_code}"}
        except Exception as e:
            results["checks"]["agent_registry"] = {"status": "error", "detail": str(e)}

    # 检查 Escrow store (via API)
    if api_ok:
        try:
            import requests as _req
            token = os.getenv("INTERNAL_TOKEN", "")
            headers = {"Authorization": f"Bearer {token}", "X-CryptoMinds-Internal-Token": token}
            r = _req.get(f"http://127.0.0.1:{api_port}/api/v1/escrow/disputed", headers=headers, timeout=5)
            if r.status_code == 200:
                disputed = len(r.json().get("orders", []))
                results["checks"]["escrow_store"] = {
                    "status": "ok",
                    "detail": f"escrow store 可用, {disputed} disputed orders",
                    "disputed_count": disputed,
                }
            else:
                results["checks"]["escrow_store"] = {"status": "error", "detail": f"API 返回 {r.status_code}"}
        except Exception as e:
            results["checks"]["escrow_store"] = {"status": "error", "detail": str(e)}

    # 检查 PostgreSQL (if DATABASE_URL configured)
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            results["checks"]["postgresql"] = {"status": "ok", "detail": "PG 连接正常"}
        except Exception as e:
            results["checks"]["postgresql"] = {"status": "error", "detail": f"PG 连接失败: {e}"}
    else:
        # SQLite check
        db_path = os.getenv("CRYPTOMINDS_DB_PATH", str(PROJECT_ROOT / "web" / "cryptominds.db"))
        sqlite_ok = Path(db_path).exists()
        results["checks"]["sqlite"] = {
            "status": "ok" if sqlite_ok else "warning",
            "detail": str(db_path) if sqlite_ok else f"文件不存在: {db_path}",
        }

    # 检查 Settlement channels
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from settlement import ChannelRegistry
        channels = ChannelRegistry.list_all()
        results["checks"]["settlement_channels"] = {
            "status": "ok" if channels else "error",
            "detail": f"{len(channels)} channels: {[c.id for c in channels]}",
            "count": len(channels),
        }
    except Exception as e:
        results["checks"]["settlement_channels"] = {"status": "error", "detail": str(e)}

    # 总体状态
    all_ok = all(c["status"] in ("ok", "warning") for c in results["checks"].values())
    any_error = any(c["status"] == "error" for c in results["checks"].values())
    results["status"] = "healthy" if all_ok and not any_error else "degraded" if not any_error else "unhealthy"

    return results


if __name__ == '__main__':
    result = check_health()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "healthy" else 1 if result["status"] == "degraded" else 2)