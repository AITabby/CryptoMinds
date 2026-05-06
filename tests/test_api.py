"""
测试 API 服务
"""

import pytest
import os

# 设置环境变量（必须在 import api_server 之前）
os.environ["CRYPTOMINDS_REQUIRE_AUTH"] = "false"
os.environ["CRYPTOMINDS_DEBUG"] = "true"

from src.api_server import app  # noqa: E402


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


def test_credit_score_cold_start(client):
    """测试信用分查询（冷启动）"""
    resp = client.get("/api/v1/credit/0x1234567890123456789012345678901234567890")
    assert resp.status_code == 200
    data = resp.get_json()
    # 冷启动应该返回 250 分
    assert data["total_score"] == 250
    assert data["grade"] == "CCC"
    assert data["is_cold_start"] is True


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
    assert data["status"] == "pending"


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


def test_escrow_lifecycle(client):
    """测试托管完整生命周期"""
    # 创建
    create_resp = client.post("/api/v1/escrow/create", json={
        "buyer": "0x1111111111111111111111111111111111111111",
        "seller": "0x2222222222222222222222222222222222222222",
        "amount": 1.0,
    })
    escrow_id = create_resp.get_json()["escrow_id"]

    # 资金托管
    fund_resp = client.post(
        f"/api/v1/escrow/{escrow_id}/fund",
        json={"tx_hash": "0xabc123"}
    )
    assert fund_resp.status_code == 200
    assert fund_resp.get_json()["status"] == "funded"

    # 交付
    deliver_resp = client.post(
        f"/api/v1/escrow/{escrow_id}/deliver",
        json={"proof": {"data": "delivery proof"}}
    )
    assert deliver_resp.status_code == 200
    assert deliver_resp.get_json()["status"] == "delivered"

    # 释放
    release_resp = client.post(f"/api/v1/escrow/{escrow_id}/release")
    assert release_resp.status_code == 200
    assert release_resp.get_json()["status"] == "settled"


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
    assert data["status"] == "pending"


def test_arbitrate_vote_and_resolve(client):
    """测试仲裁投票和解决"""
    # 创建托管
    create_resp = client.post("/api/v1/escrow/create", json={
        "buyer": "0x1111111111111111111111111111111111111111",
        "seller": "0x2222222222222222222222222222222222222222",
        "amount": 1.0,
    })
    escrow_id = create_resp.get_json()["escrow_id"]

    # 创建争议
    dispute_resp = client.post("/api/v1/arbitrate/submit", json={
        "escrow_id": escrow_id,
        "reason": "测试争议"
    })
    dispute_id = dispute_resp.get_json()["dispute_id"]

    # 投票
    vote_resp = client.post(f"/api/v1/arbitrate/{dispute_id}/vote", json={
        "arbitrator": "0x3333333333333333333333333333333333333333",
        "vote": "seller",
        "weight": 1.0
    })
    assert vote_resp.status_code == 200

    # 解决
    resolve_resp = client.post(f"/api/v1/arbitrate/{dispute_id}/resolve", json={
        "result": "seller_wins",
        "reason": "卖家胜诉"
    })
    assert resolve_resp.status_code == 200
    assert resolve_resp.get_json()["status"] == "resolved"
