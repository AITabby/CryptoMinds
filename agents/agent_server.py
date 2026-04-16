#!/usr/bin/env python3
"""
CryptoMinds Agent 微服务
每个 Agent 独立运行，通过 HTTP 提供服务
业务逻辑从 agent_runtimes/ 导入，本文件只管 HTTP 层

启动方式:
  python3 agents/agent_server.py --agent tiedan --port 5001
  python3 agents/agent_server.py --agent choudan --port 5002
  python3 agents/agent_server.py --agent ludan --port 5003
  python3 agents/agent_server.py --agent four_meme --port 5004
"""

import json
import time
import sys
import os
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

# 声誉系统
try:
    from agents.agent_reputation import get_reputation_system
    REPUTATION_ENABLED = True
except ImportError:
    REPUTATION_ENABLED = False

# x402 验证
import os
DEMO_MODE = os.getenv("CRYPTOMINDS_DEMO", "0") == "1"
try:
    from x402_pay import verify_x402_payment as _verify_x402
    X402_VERIFY_ENABLED = True
except ImportError:
    X402_VERIFY_ENABLED = False

# Agent Runtime 模块
try:
    from agent_runtimes import RUNTIMES
    RUNTIMES_AVAILABLE = True
except ImportError:
    RUNTIMES_AVAILABLE = False
    print("⚠️ agent_runtimes 不可用，Agent 将无法执行任务")


def _load_wallets():
    wallets_file = os.path.join(DIR, "wallets.json")
    try:
        with open(wallets_file) as f:
            return json.load(f)
    except Exception:
        return {}


# Agent 服务价格表 (USDC)
SERVICE_PRICES = {
    "tiedan": 0.15,
    "choudan": 0.09,
    "ludan": 0.03,
    "four_meme": 0.12,
}


class AgentHandler(BaseHTTPRequestHandler):
    """通用 Agent HTTP 处理器"""

    agent_name = "unknown"
    agent_port = 5000

    def log_message(self, format, *args):
        print(f"  [{self.agent_name}:{self.agent_port}] {args[0]}")

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"ok": True, "agent": self.agent_name, "port": self.agent_port})
        elif self.path == "/info":
            response = {
                "agent": self.agent_name,
                "port": self.agent_port,
                "status": "ready",
                "uptime": time.time() - START_TIME,
            }
            if REPUTATION_ENABLED:
                try:
                    rs = get_reputation_system()
                    response["reputation"] = rs.get_reputation(self.agent_name)
                except Exception as e:
                    response["reputation_error"] = str(e)
            self._respond(200, response)
        elif self.path == "/reputation":
            if REPUTATION_ENABLED:
                try:
                    rs = get_reputation_system()
                    self._respond(200, rs.get_reputation(self.agent_name))
                except Exception as e:
                    self._respond(500, {"error": str(e)})
            else:
                self._respond(503, {"error": "声誉系统未启用"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/execute":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._respond(400, {"error": "invalid JSON"})
                return

            task = payload.get("task", "")
            token_address = payload.get("token_address")
            request_id = payload.get("request_id", f"req-{int(time.time())}")
            payment_info = payload.get("payment")

            print(f"  📥 [{self.agent_name}] 收到任务: {task}")

            # x402 支付验证（demo 模式跳过）
            if DEMO_MODE:
                pass
            elif payment_info:
                if X402_VERIFY_ENABLED:
                    valid, msg = _verify_x402(payment_info)
                else:
                    valid, msg = True, "x402 验证模块不可用，跳过"
                if not valid:
                    self._respond(402, {
                        "request_id": request_id,
                        "agent": self.agent_name,
                        "success": False,
                        "error": f"支付验证失败: {msg}",
                        "x402_required": True,
                        "price": SERVICE_PRICES.get(self.agent_name, 0.1)
                    })
                    return
            elif not DEMO_MODE:
                price = SERVICE_PRICES.get(self.agent_name, 0.1)
                self._respond(402, {
                    "request_id": request_id,
                    "agent": self.agent_name,
                    "success": False,
                    "error": "需要支付",
                    "x402_required": True,
                    "price": price,
                    "payment_address": _load_wallets().get(self.agent_name, {}).get("address", ""),
                    "token": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
                    "chain": "bsc"
                })
                return

            start_time = time.time()
            success = False
            error_message = None

            try:
                result = self._execute_task(task, token_address)
                success = True
                self._respond(200, {
                    "request_id": request_id,
                    "agent": self.agent_name,
                    "success": True,
                    "data": result,
                    "timestamp": time.time(),
                    "payment_verified": True,
                    "tx_hash": payment_info.get("tx_hash") if payment_info else None
                })
            except Exception as e:
                error_message = str(e)
                success = False
                self._respond(500, {
                    "request_id": request_id,
                    "agent": self.agent_name,
                    "success": False,
                    "error": str(e),
                })
            finally:
                if REPUTATION_ENABLED:
                    try:
                        rs = get_reputation_system()
                        rs.record_transaction(
                            agent_name=self.agent_name,
                            success=success,
                            response_time=time.time() - start_time,
                            error_message=error_message,
                            request_id=request_id
                        )
                    except Exception:
                        pass
        else:
            self._respond(404, {"error": "not found"})

    def _execute_task(self, task, token_address=None):
        """从 agent_runtimes 导入执行"""
        if not RUNTIMES_AVAILABLE:
            raise RuntimeError("agent_runtimes 不可用")
        
        runtime_fn = RUNTIMES.get(self.agent_name)
        if not runtime_fn:
            raise RuntimeError(f"未知 Agent runtime: {self.agent_name}")
        
        return runtime_fn(task_description=task, token_address=token_address)

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


# Agent → 端口映射
AGENT_PORTS = {
    "tiedan": 5001,
    "choudan": 5002,
    "ludan": 5003,
    "four_meme": 5004,
}

START_TIME = time.time()


def main():
    parser = argparse.ArgumentParser(description="CryptoMinds Agent 微服务")
    parser.add_argument("--agent", required=True, choices=list(AGENT_PORTS.keys()))
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port or AGENT_PORTS[args.agent]
    AgentHandler.agent_name = args.agent
    AgentHandler.agent_port = port

    server = HTTPServer(("0.0.0.0", port), AgentHandler)
    print(f"🚀 {args.agent} Agent 启动 → http://localhost:{port}")
    print(f"   健康检查: GET /health")
    print(f"   执行任务: POST /execute")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n🛑 {args.agent} Agent 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
