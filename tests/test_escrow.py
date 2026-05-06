"""
测试托管状态流转
"""

import pytest
from src.api_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestEscrowFlow:
    """托管完整流程测试"""

    def test_create_escrow(self, client):
        """测试创建托管"""
        resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 1.0,
            "token": "BNB",
            "timeout": 86400
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "pending"
        assert data["buyer"] == "0x1111111111111111111111111111111111111111"
        assert data["seller"] == "0x2222222222222222222222222222222222222222"
        assert float(data["amount"]) == 1.0

    def test_fund_escrow(self, client):
        """测试资金托管"""
        # 创建
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]

        # 托管资金
        fund_resp = client.post(f"/api/v1/escrow/{escrow_id}/fund", json={
            "tx_hash": "0xabcdef1234567890"
        })
        assert fund_resp.status_code == 200
        data = fund_resp.get_json()
        assert data["status"] == "funded"
        assert data["fund_tx"] == "0xabcdef1234567890"

    def test_deliver_escrow(self, client):
        """测试交付"""
        # 创建并托管
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        client.post(f"/api/v1/escrow/{escrow_id}/fund", json={
            "tx_hash": "0xabc123"
        })

        # 交付
        deliver_resp = client.post(f"/api/v1/escrow/{escrow_id}/deliver", json={
            "proof": {
                "type": "transaction",
                "tx_hash": "0xdelivery123"
            }
        })
        assert deliver_resp.status_code == 200
        data = deliver_resp.get_json()
        assert data["status"] == "delivered"

    def test_release_escrow(self, client):
        """测试释放资金"""
        # 完整流程：创建 → 托管 → 交付 → 释放
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        client.post(f"/api/v1/escrow/{escrow_id}/fund", json={"tx_hash": "0xabc"})
        client.post(f"/api/v1/escrow/{escrow_id}/deliver", json={"proof": {"tx": "0xdel"}})

        # 释放
        release_resp = client.post(f"/api/v1/escrow/{escrow_id}/release")
        assert release_resp.status_code == 200
        data = release_resp.get_json()
        assert data["status"] == "settled"

    def test_refund_escrow(self, client):
        """测试退款"""
        # 创建并托管
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        client.post(f"/api/v1/escrow/{escrow_id}/fund", json={"tx_hash": "0xabc"})

        # 退款
        refund_resp = client.post(f"/api/v1/escrow/{escrow_id}/refund")
        assert refund_resp.status_code == 200
        data = refund_resp.get_json()
        assert data["status"] == "refunded"

    def test_escrow_not_found(self, client):
        """测试查询不存在的托管"""
        resp = client.get("/api/v1/escrow/nonexistent_id")
        assert resp.status_code == 404

    def test_deliver_wrong_state(self, client):
        """测试错误状态下交付"""
        # 创建但不托管，直接尝试交付
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]

        # 尝试交付（应该失败，因为还没托管）
        deliver_resp = client.post(f"/api/v1/escrow/{escrow_id}/deliver", json={
            "proof": {"tx": "0xdel"}
        })
        assert deliver_resp.status_code == 400

    def test_release_wrong_state(self, client):
        """测试错误状态下释放"""
        # 创建并托管，但不交付
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        client.post(f"/api/v1/escrow/{escrow_id}/fund", json={"tx_hash": "0xabc"})

        # 尝试释放（应该失败，因为还没交付）
        release_resp = client.post(f"/api/v1/escrow/{escrow_id}/release")
        assert release_resp.status_code == 400


class TestEscrowValidation:
    """托管参数验证测试"""

    def test_create_missing_buyer(self, client):
        """测试缺少买家参数"""
        resp = client.post("/api/v1/escrow/create", json={
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        assert resp.status_code == 400

    def test_create_missing_seller(self, client):
        """测试缺少卖家参数"""
        resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "amount": 0.5
        })
        assert resp.status_code == 400

    def test_create_missing_amount(self, client):
        """测试缺少金额参数"""
        resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222"
        })
        assert resp.status_code == 400

    def test_create_with_metadata(self, client):
        """测试带元数据创建"""
        resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5,
            "metadata": {
                "service": "token_delivery",
                "description": "测试服务"
            }
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["metadata"]["service"] == "token_delivery"
