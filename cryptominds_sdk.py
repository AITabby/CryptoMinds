#!/usr/bin/env python3
"""
CryptoMinds 轻量 SDK — 任何 Agent 只需 3 行代码接入

用法:
    from cryptominds_sdk import CryptoMinds

    cm = CryptoMinds("http://localhost:3456", wallet="0x你的钱包地址")
    
    # 发现
    skills = cm.discover("扫链")
    
    # 购买 + 执行
    result = cm.buy_and_run("tiedan-scan")
"""

import json
import urllib.request
import urllib.error


class CryptoMinds:
    """CryptoMinds Agent SDK — 纯 HTTP，零依赖"""
    
    def __init__(self, api_url="http://localhost:3456", wallet=None, name=None, payment_mode="demo"):
        """
        Args:
            api_url:    CryptoMinds API 地址
            wallet:     Agent 钱包地址
            name:       Agent 名称（可选）
            payment_mode: "demo"（演示）或 "onchain"（真实链上）
        """
        self.api_url = api_url.rstrip("/")
        self.wallet = wallet
        self.name = name or "agent"
        self.payment_mode = payment_mode
    
    def _get(self, path):
        resp = urllib.request.urlopen(f"{self.api_url}{path}", timeout=10)
        return json.loads(resp.read())
    
    def _post(self, path, data):
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    
    # ── 核心 3 接口 ──
    
    def discover(self, query=None):
        """发现市场 Skill，可选关键词过滤"""
        data = self._get("/api/market")
        skills = data if isinstance(data, list) else data.get("services", data.get("data", []))
        if query:
            q = query.lower()
            skills = [s for s in skills if q in s.get("name", "").lower()
                      or q in s.get("desc", "").lower()
                      or q in s.get("expert", "").lower()]
        return skills
    
    def buy(self, skill_id, tx_hash=None):
        """购买 Skill"""
        if not self.wallet:
            raise ValueError("未设置钱包地址，请初始化时传入 wallet")
        payload = {
            "serviceId": skill_id,
            "buyerWallet": self.wallet,
            "buyerName": self.name,
            "paymentMode": self.payment_mode,
        }
        if tx_hash:
            payload["txHash"] = tx_hash
        result = self._post("/api/services/buy", payload)
        return result
    
    def call(self, skill_id, task=None):
        """调用已购买的 Skill"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        payload = {"buyer": self.wallet}
        if task:
            payload["task"] = task
        return self._post(f"/api/skill/call/{skill_id}", payload)
    
    def buy_and_run(self, skill_id, task=None, tx_hash=None):
        """一步完成：购买 + 拿结果（最常用）"""
        buy_result = self.buy(skill_id, tx_hash=tx_hash)
        if not buy_result.get("ok"):
            return buy_result
        # 购买时已执行 runtime，结果在 purchase.report 里
        purchase = buy_result.get("purchase", {})
        if purchase.get("report"):
            return {"ok": True, "source": "purchase", "data": purchase["report"]}
        # 否则尝试调用
        return self.call(skill_id, task=task)
    
    # ── 辅助接口 ──
    
    def register_agent(self, framework="generic"):
        """注册 Agent 身份"""
        return self._post("/api/agents/register", {
            "name": self.name,
            "wallet": self.wallet,
            "framework": framework,
        })
    
    def register_expert(self, name, desc, price, deposit, endpoint=None, **kwargs):
        """注册为专家，提交 Skill"""
        payload = {
            "expert": self.name,
            "wallet": self.wallet,
            "name": name,
            "desc": desc,
            "price": price,
            "deposit": deposit,
            "frameworks": kwargs.get("frameworks", ["generic"]),
        }
        if endpoint:
            payload["endpoint"] = endpoint
        return self._post("/api/experts/register", payload)
    
    def my_skills(self):
        """查看已购买的 Skill"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        return self._get(f"/api/agents/{self.wallet}/skills")
    
    def smart_route(self, skill_id):
        """查询最优支付路径"""
        return self._post("/api/smart-route", {
            "walletAddress": self.wallet,
            "serviceId": skill_id,
        })
    
    def health(self):
        """健康检查"""
        return self._get("/healthz")


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys
    
    cm = CryptoMinds(
        api_url="http://localhost:3456",
        wallet="0xd2f899CE74320AEf9d8f2359183232a554f4C0E1",
        name="gangdan",
    )
    
    if len(sys.argv) < 2:
        print("用法: python cryptominds_sdk.py [discover|buy|run|health] [skill_id]")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "health":
        print(cm.health())
    elif cmd == "discover":
        skills = cm.discover(sys.argv[2] if len(sys.argv) > 2 else None)
        for s in skills:
            print(f"  {s['id']}: {s['name']} by {s['expert']} @{s['price']} BNB")
    elif cmd == "buy":
        sid = sys.argv[2] if len(sys.argv) > 2 else "tiedan-scan"
        result = cm.buy(sid)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "run":
        sid = sys.argv[2] if len(sys.argv) > 2 else "tiedan-scan"
        result = cm.buy_and_run(sid)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
