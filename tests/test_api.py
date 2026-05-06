"""
测试 API 服务
"""

import pytest
from src.api_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    """测试健康检查"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"


def test_info(client):
    """测试信息接口"""
    resp = client.get("/api/v1/info")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "CryptoMinds"


def test_escrow_create(client):
    """测试创建托管"""
    resp = client.post("/api/v1/escrow/create", json={
        "buyer": "0x1234567890123456789012345678901234567890",
        "seller": "0x0987654321098765432109876543210987654321",
        "amount": 0.1,
        "token": "BNB"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "escrow_id" in data
    assert data["state"] == "created"


def test_escrow_get(client):
    """测试查询托管"""
    # 先创建
    create_resp = client.post("/api/v1/escrow/create", json={
        "buyer": "0x1234567890123456789012345678901234567890",
        "seller": "0x0987654321098765432109876543210987654321",
        "amount": 0.1
    })
    escrow_id = create_resp.get_json()["escrow_id"]

    # 再查询
    resp = client.get(f"/api/v1/escrow/{escrow_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["escrow_id"] == escrow_id


def test_arbitrate_submit(client):
    """测试提交争议"""
    # 先创建托管
    create_resp = client.post("/api/v1/escrow/create", json={
        "buyer": "0x1234567890123456789012345678901234567890",
        "seller": "0x0987654321098765432109876543210987654321",
        "amount": 0.1
    })
    escrow_id = create_resp.get_json()["escrow_id"]

    # 提交争议
    resp = client.post("/api/v1/arbitrate/submit", json={
        "escrow_id": escrow_id,
        "reason": "测试争议"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dispute_id" in data
    assert data["state"] == "pending"
