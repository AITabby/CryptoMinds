"""
Agent 事件推送 — 把 Agent 思考过程推送到 Dashboard Live Feed
用法:
    from agent_events import think, pay, execute, result

    think("Buyer Agent", "用户给了买币意图，开始搜索卖家")
    pay("Buyer Agent", "Momentum One", 0.000124, "支付执行费", tx_hash="0x...")
    execute("Momentum One", "执行买币中...")
    result("Momentum One", "已完成买币并回传结果")
"""
import os
import json
import time
import datetime
import requests

MARKET_URL = os.getenv("CRYPTOMINDS_MARKET", "http://localhost:3457")
DISABLED = os.getenv("CRYPTOMINDS_EVENTS_OFF", "") == "1"

def _push(event_type, agent, message, **kwargs):
    """推送事件到 dashboard"""
    if DISABLED:
        return
    try:
        payload = {
            "type": event_type,  # think | pay | execute | result | error
            "agent": agent,
            "message": message,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
        payload.update(kwargs)
        requests.post(f"{MARKET_URL}/api/agent-events", json=payload, timeout=2)
    except Exception:
        pass  # 静默失败，不影响主流程

def think(agent, message):
    """Agent 思考"""
    _push("think", agent, message)

def pay(agent, to_agent, amount, reason, tx_hash=None):
    """Agent 支付"""
    _push("pay", agent, f"→ {to_agent} {amount} BNB: {reason}",
          to=to_agent, amount=amount, tx_hash=tx_hash)

def execute(agent, message):
    """Agent 执行"""
    _push("execute", agent, message)

def result(agent, message):
    """Agent 结果"""
    _push("result", agent, message)

def error(agent, message):
    """Agent 错误"""
    _push("error", agent, message)
