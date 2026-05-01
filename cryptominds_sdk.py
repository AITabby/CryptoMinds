#!/usr/bin/env python3
"""
CryptoMinds 轻量 SDK — Agent 链上雇佣市场

用法:
    from cryptominds_sdk import CryptoMinds

    cm = CryptoMinds("http://localhost:3457", wallet="0x你的钱包地址")

    # 发现卖家
    sellers = cm.search_sellers("meme")

    # 创建订单（买家下单）
    order = cm.create_order(seller_wallet, amount_bnb=0.001)

    # 卖家注册
    cm.register_seller(name="扫链卖家", desc="BSC链上扫描", price=0.001, endpoint="http://localhost:5001")

    # 查看订单
    orders = cm.get_orders()
"""

import json
import urllib.request
import urllib.error


class CryptoMinds:
    """CryptoMinds Agent SDK — 纯 HTTP，零依赖"""

    def __init__(self, api_url="http://localhost:3457", wallet=None, name=None):
        """
        Args:
            api_url:    CryptoMinds API 地址
            wallet:     Agent 钱包地址
            name:       Agent 名称（可选）
        """
        self.api_url = api_url.rstrip("/")
        self.wallet = wallet
        self.name = name or "agent"

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

    # ── 买家接口 ──

    def search_sellers(self, query=None):
        """搜索卖家市场，可选关键词过滤"""
        data = self._get("/api/v1/market")
        sellers = data.get("sellers", data if isinstance(data, list) else [])
        if query:
            q = query.lower()
            sellers = [s for s in sellers if q in s.get("name", "").lower()
                       or q in s.get("desc", "").lower()]
        return sellers

    def create_order(self, seller_wallet, amount_bnb):
        """创建订单（买家向卖家下单）"""
        if not self.wallet:
            raise ValueError("未设置钱包地址，请初始化时传入 wallet")
        return self._post("/api/v1/orders/create", {
            "buyerWallet": self.wallet,
            "sellerWallet": seller_wallet,
            "amount": amount_bnb,
        })

    def auto_buy(self, amount_bnb):
        """Agent 自动匹配卖家并下单"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        return self._post("/api/v1/agent-buy", {
            "buyerWallet": self.wallet,
            "amount": amount_bnb,
        })

    def get_orders(self, wallet=None):
        """查看我的订单"""
        addr = wallet or self.wallet
        if not addr:
            raise ValueError("未设置钱包地址")
        return self._get(f"/api/v1/my-orders?wallet={addr}")

    def confirm_purchase(self, purchase_id, rating=None):
        """确认收货，可选评分"""
        payload = {}
        if rating:
            payload["rating"] = rating
        return self._post(f"/api/v1/purchases/confirm/{purchase_id}", payload)

    # ── 卖家接口 ──

    def register_seller(self, name, desc, price, endpoint, deposit_tx=None):
        """注册为卖家（endpoint必填）"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        payload = {
            "name": name,
            "desc": desc,
            "price": price,
            "wallet": self.wallet,
            "endpoint": endpoint,
        }
        if deposit_tx:
            payload["depositTx"] = deposit_tx
        return self._post("/api/v1/sellers/register", payload)

    def deposit(self, amount_bnb):
        """追加押金"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        return self._post(f"/api/v1/sellers/{self.wallet}/deposit", {"amount": amount_bnb})

    def exit_market(self):
        """退出市场，退回押金"""
        if not self.wallet:
            raise ValueError("未设置钱包地址")
        return self._post("/api/v1/sellers/exit", {"wallet": self.wallet})

    def deliver_result(self, order_id, result):
        """提交执行结果"""
        return self._post(f"/api/v1/orders/{order_id}/result", {"result": result})

    # ── 通用接口 ──

    def get_market(self):
        """市场概览"""
        return self._get("/api/v1/market")

    def smart_route(self, seller_id):
        """查询最优支付路径"""
        return self._post("/api/v1/smart-route", {
            "walletAddress": self.wallet,
            "serviceId": seller_id,
        })

    def health(self):
        """健康检查"""
        return self._get("/healthz")


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys

    cm = CryptoMinds(
        api_url="http://localhost:3457",
        wallet="0xd2f899CE74320AEf9d8f2359183232a554f4C0E1",
        name="gangdan",
    )

    if len(sys.argv) < 2:
        print("用法: python cryptominds_sdk.py [search|buy|orders|health] [args...]")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "health":
        print(cm.health())
    elif cmd == "search":
        sellers = cm.search_sellers(sys.argv[2] if len(sys.argv) > 2 else None)
        for s in sellers:
            print(f"  {s.get('name','?')} — 评分:{s.get('rating',0):.1f} 权重:{s.get('weight',0):.2f} 价格:{s.get('price',0)} BNB")
    elif cmd == "buy":
        amount = float(sys.argv[2]) if len(sys.argv) > 2 else 0.001
        result = cm.auto_buy(amount)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "orders":
        orders = cm.get_orders()
        print(json.dumps(orders, indent=2, ensure_ascii=False, default=str))
