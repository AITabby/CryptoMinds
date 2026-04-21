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

    # 检查 wallets.json（相对于项目根目录）
    project_root = Path(__file__).parent.parent
    wallets_ok = (project_root / 'wallets.json').exists()
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

    # 总体状态
    all_ok = all(c["status"] == "ok" for c in results["checks"].values())
    results["status"] = "healthy" if all_ok else "degraded"

    return results


if __name__ == '__main__':
    result = check_health()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "healthy" else 1)
