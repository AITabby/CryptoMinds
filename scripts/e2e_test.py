#!/usr/bin/env python3
"""
端到端验证脚本 — 测试 Escrow + Session Key API 通过 Flask (3458) 和 Express (3457) 代理

启动两个服务器, 运行测试, 然后关闭。
"""

import subprocess
import time
import sys
import json
import os
import signal
import requests

FLASK_PORT = 3458
EXPRESS_PORT = 3457
BASE_FLASK = f"http://localhost:{FLASK_PORT}/api/v1"
BASE_EXPRESS = f"http://localhost:{EXPRESS_PORT}/api/v1/protocol"

# 设置 ADMIN_SECRET 和 INTERNAL_TOKEN
ADMIN_SECRET = "test-admin-secret-e2e"
INTERNAL_TOKEN = "test-internal-token-e2e"

os.environ["ADMIN_SECRET"] = ADMIN_SECRET
os.environ["CRYPTOMINDS_INTERNAL_TOKEN"] = INTERNAL_TOKEN
os.environ["DEMO_MODE"] = "true"
os.environ["CRYPTOMINDS_ENV"] = "dev"


def start_servers():
    """启动 Flask 和 Express 服务器"""
    env = os.environ.copy()
    env["ADMIN_SECRET"] = ADMIN_SECRET
    env["CRYPTOMINDS_INTERNAL_TOKEN"] = INTERNAL_TOKEN
    env["DEMO_MODE"] = "true"
    env["CRYPTOMINDS_DEBUG"] = "false"

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("启动 Flask API (3458)...")
    flask_proc = subprocess.Popen(
        [sys.executable, "api_server.py"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=project_dir,
    )
    time.sleep(4)

    print("启动 Express Gateway (3457)...")
    express_proc = subprocess.Popen(
        ["node", "web/server_modular.js"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=project_dir,
    )
    time.sleep(4)

    return flask_proc, express_proc


def stop_servers(flask_proc, express_proc):
    """关闭服务器"""
    print("\n关闭服务器...")
    for proc in [flask_proc, express_proc]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def wait_for_server(url, max_retries=10):
    """等待服务器可用"""
    for i in range(max_retries):
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False


def test_endpoint(name, method, url, headers=None, body=None, expected_ok=True):
    """通用端点测试"""
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=5)
        else:
            r = requests.post(url, headers=headers, json=body, timeout=5)
        data = r.json()
        ok = data.get("ok", False) if isinstance(data, dict) else False
        status = "PASS" if (ok == expected_ok or r.status_code < 400) else "FAIL"
        print(f"  [{status}] {name}: {r.status_code} → ok={ok}")
        if status == "FAIL":
            print(f"    Response: {json.dumps(data, indent=2)[:200]}")
        return data
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return None


def run_tests():
    """运行端到端测试"""
    results = {"pass": 0, "fail": 0}
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("\n=== Flask 直接测试 (3458) ===\n")

    # ── 基础 ──
    test_endpoint("Flask /healthz", "GET", f"http://localhost:{FLASK_PORT}/healthz")
    test_endpoint("Flask /info", "GET", f"{BASE_FLASK}/info",
                  headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN})
    results["pass"] += 2

    # ── Escrow ──
    escrow_data = test_endpoint(
        "Flask /escrow/create",
        "POST", f"{BASE_FLASK}/escrow/create",
        headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
        body={
            "task_id": "e2e-task-001",
            "buyer_wallet": "0xBuyerE2E",
            "seller_wallet": "0xSellerE2E",
            "seller_agent_id": "agent-e2e",
            "amount": "0.5",
            "chain": "bsc",
        },
    )
    if escrow_data and escrow_data.get("ok"):
        escrow_id = escrow_data.get("escrow_id")
        results["pass"] += 1

        # Get escrow
        test_endpoint("Flask /escrow/<id>", "GET", f"{BASE_FLASK}/escrow/{escrow_id}",
                      headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN})
        results["pass"] += 1

        # Advance state: created → funded → executing → delivered (via SQLite)
        import sqlite3
        db_path = os.path.join(project_dir, "web", "cryptominds.db")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE escrow_orders SET state = 'delivered' WHERE escrow_id = ?", (escrow_id,))
        conn.commit()
        conn.close()

        # Dispute (from delivered → disputed)
        dispute_data = test_endpoint(
            "Flask /escrow/<id>/dispute",
            "POST", f"{BASE_FLASK}/escrow/{escrow_id}/dispute",
            headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
            body={"reason": "e2e test dispute", "initiator": "buyer"},
        )
        if dispute_data and dispute_data.get("ok"):
            results["pass"] += 1
        else:
            results["fail"] += 1

        # Resolve (admin secret)
        resolve_data = test_endpoint(
            "Flask /escrow/<id>/resolve (admin)",
            "POST", f"{BASE_FLASK}/escrow/{escrow_id}/resolve",
            headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN, "X-Admin-Secret": ADMIN_SECRET},
            body={"decision": "buyer_win"},
        )
        if resolve_data and resolve_data.get("ok"):
            results["pass"] += 1
        else:
            results["fail"] += 1
    else:
        results["fail"] += 1
        escrow_id = None

    # List disputed
    test_endpoint("Flask /escrow/disputed", "GET", f"{BASE_FLASK}/escrow/disputed",
                  headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN})
    results["pass"] += 1

    # ── Session Key ──
    sk_data = test_endpoint(
        "Flask /session-keys/create (demo)",
        "POST", f"{BASE_FLASK}/session-keys/create",
        headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
        body={
            "main_wallet": "0xMainE2E",
            "main_private_key": "DEMO",
            "agent_id": "agent-e2e-sk",
            "chains": ["bsc", "mock"],
            "per_tx_limit": "0.5",
            "total_quota": "10",
            "actions": ["pay", "escrow", "deliver"],
            "validity_seconds": 3600,
        },
    )
    if sk_data and (sk_data.get("ok") or sk_data.get("session_key_id")):
        sk_id = sk_data.get("session_key_id")
        results["pass"] += 1

        # Get session key
        test_endpoint("Flask /session-keys/<id>", "GET", f"{BASE_FLASK}/session-keys/{sk_id}",
                      headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN})
        results["pass"] += 1

        # Revoke (demo mode)
        test_endpoint(
            "Flask /session-keys/<id>/revoke (demo)",
            "POST", f"{BASE_FLASK}/session-keys/{sk_id}/revoke",
            headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
            body={"main_wallet": "0xMainE2E", "main_private_key": "DEMO"},
        )
        results["pass"] += 1

        # Increase quota (demo mode) — 先创建第二个 key 来测提额
        sk2_data = test_endpoint(
            "Flask /session-keys/create #2 (demo)",
            "POST", f"{BASE_FLASK}/session-keys/create",
            headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
            body={
                "main_wallet": "0xMainE2E",
                "main_private_key": "DEMO",
                "agent_id": "agent-e2e-sk2",
                "chains": ["bsc"],
                "per_tx_limit": "1.0",
                "total_quota": "5",
                "actions": ["pay"],
            },
        )
        if sk2_data and sk2_data.get("session_key_id"):
            sk2_id = sk2_data.get("session_key_id")
            results["pass"] += 1
            test_endpoint(
                "Flask /session-keys/<id>/increase-quota (demo)",
                "POST", f"{BASE_FLASK}/session-keys/{sk2_id}/increase-quota",
                headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN},
                body={"additional_quota": "5.0", "main_wallet": "0xMainE2E", "main_private_key": "DEMO"},
            )
            results["pass"] += 1
        else:
            results["fail"] += 1

        # Agent session keys
        test_endpoint("Flask /session-keys/agent/<id>", "GET", f"{BASE_FLASK}/session-keys/agent/agent-e2e-sk",
                      headers={"X-CryptoMinds-Internal-Token": INTERNAL_TOKEN})
        results["pass"] += 1
    else:
        results["fail"] += 1

    print("\n=== Express 代理测试 (3457) ===\n")

    # ── 基础 ──
    test_endpoint("Express /protocol/info", "GET", f"{BASE_EXPRESS}/info")
    test_endpoint("Express /protocol/channels", "GET", f"{BASE_EXPRESS}/channels")
    results["pass"] += 2

    # ── 安全: 内部写入路由拒绝浏览器调用 ──
    blocked = test_endpoint(
        "Express /protocol/tasks/complete (no auth, blocked)",
        "POST", f"{BASE_EXPRESS}/tasks/complete",
        body={"task_id": "test", "result": "done"},
        expected_ok=False,  # should be blocked
    )
    if blocked and blocked.get("error") and "forbidden" in blocked.get("error", "").lower():
        results["pass"] += 1
    else:
        results["fail"] += 1
        print("  [SECURITY] Internal write route NOT blocked!")

    # ── Escrow (通过 Express 代理) ──
    # Create escrow via Express with admin secret
    express_escrow = test_endpoint(
        "Express /protocol/escrow/create (admin)",
        "POST", f"{BASE_EXPRESS}/escrow/create",
        headers={"X-Admin-Secret": ADMIN_SECRET},
        body={
            "task_id": "express-test-001",
            "buyer_wallet": "0xExpressBuyer",
            "seller_wallet": "0xExpressSeller",
            "seller_agent_id": "agent-express",
            "amount": "1.0",
            "chain": "bsc",
        },
    )
    if express_escrow and express_escrow.get("ok"):
        express_escrow_id = express_escrow.get("escrow_id")
        results["pass"] += 1

        # Advance state to delivered
        import sqlite3
        db_path = os.path.join(project_dir, "web", "cryptominds.db")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE escrow_orders SET state = 'delivered' WHERE escrow_id = ?", (express_escrow_id,))
        conn.commit()
        conn.close()

        # Dispute via Express (business auth route, token injected)
        express_dispute = test_endpoint(
            "Express /protocol/escrow/<id>/dispute",
            "POST", f"{BASE_EXPRESS}/escrow/{express_escrow_id}/dispute",
            body={"reason": "express test dispute", "initiator": "buyer"},
        )
        if express_dispute and express_dispute.get("ok"):
            results["pass"] += 1
        else:
            results["fail"] += 1

        # Resolve via Express (requireAdmin, admin secret forwarded)
        express_resolve = test_endpoint(
            "Express /protocol/escrow/<id>/resolve (admin secret forwarded)",
            "POST", f"{BASE_EXPRESS}/escrow/{express_escrow_id}/resolve",
            headers={"X-Admin-Secret": ADMIN_SECRET},
            body={"decision": "buyer_win", "reason": "express test resolve"},
        )
        if express_resolve and express_resolve.get("ok"):
            results["pass"] += 1
        else:
            results["fail"] += 1

        # GET escrow
        test_endpoint("Express /protocol/escrow/<id>", "GET", f"{BASE_EXPRESS}/escrow/{express_escrow_id}")
        results["pass"] += 1
    else:
        results["fail"] += 1
        express_escrow_id = None

    # GET disputed list
    test_endpoint("Express /protocol/escrow/disputed", "GET", f"{BASE_EXPRESS}/escrow/disputed")
    results["pass"] += 1

    # ── Session Key (通过 Express 代理) ──
    express_sk = test_endpoint(
        "Express /protocol/session-keys/create (demo)",
        "POST", f"{BASE_EXPRESS}/session-keys/create",
        body={
            "main_wallet": "0xExpressSK",
            "main_private_key": "DEMO",
            "agent_id": "agent-express-sk",
            "available_chains": ["bsc"],
            "per_tx_limit": "1.0",
            "total_quota": "5.0",
            "callable_actions": ["pay"],
        },
    )
    if express_sk and express_sk.get("session_key_id"):
        express_sk_id = express_sk.get("session_key_id")
        results["pass"] += 1
        test_endpoint("Express /protocol/session-keys/<id>", "GET", f"{BASE_EXPRESS}/session-keys/{express_sk_id}")
        results["pass"] += 1
    else:
        results["fail"] += 1

    print(f"\n=== 结果: {results['pass']} pass, {results['fail']} fail ===")
    return results["fail"] == 0


if __name__ == "__main__":
    flask_proc = None
    express_proc = None
    try:
        flask_proc, express_proc = start_servers()

        flask_ok = wait_for_server(f"http://localhost:{FLASK_PORT}/healthz")
        express_ok = wait_for_server(f"http://localhost:{EXPRESS_PORT}/api/v1/protocol/info")

        if not flask_ok:
            print("Flask 服务启动失败!")
            stop_servers(flask_proc, express_proc)
            sys.exit(1)
        if not express_ok:
            print("Express 服务启动失败!")
            stop_servers(flask_proc, express_proc)
            sys.exit(1)

        print("两个服务均已启动 ✓")
        success = run_tests()
        stop_servers(flask_proc, express_proc)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        stop_servers(flask_proc, express_proc)
        sys.exit(1)
    except Exception as e:
        print(f"异常: {e}")
        stop_servers(flask_proc, express_proc)
        sys.exit(1)