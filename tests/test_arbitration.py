"""
测试争议仲裁
"""

import pytest
from src.api_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestArbitration:
    """争议仲裁测试"""

    def test_submit_dispute(self, client):
        """测试提交争议"""
        # 先创建托管
        escrow_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 1.0
        })
        escrow_id = escrow_resp.get_json()["escrow_id"]

        # 提交争议
        resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "未按时交付",
            "evidence": {"tx": "0xevidence1"}
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "pending"
        assert data["escrow_id"] == escrow_id

    def test_get_dispute(self, client):
        """测试查询争议"""
        # 创建托管并提交争议
        escrow_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = escrow_resp.get_json()["escrow_id"]

        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "质量问题"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        # 查询
        resp = client.get(f"/api/v1/arbitrate/{dispute_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dispute_id"] == dispute_id
        assert data["reason"] == "质量问题"

    def test_add_evidence(self, client):
        """测试添加证据"""
        # 创建争议
        escrow_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = escrow_resp.get_json()["escrow_id"]

        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "测试"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        # 添加证据
        resp = client.post(f"/api/v1/arbitrate/{dispute_id}/evidence", json={
            "type": "screenshot",
            "url": "https://example.com/evidence.png"
        })
        assert resp.status_code == 200

    def test_get_arbitrators(self, client):
        """测试查询仲裁员"""
        escrow_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = escrow_resp.get_json()["escrow_id"]

        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "测试"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        resp = client.get(f"/api/v1/arbitrate/{dispute_id}/arbitrators")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "arbitrators" in data

    def test_dispute_not_found(self, client):
        """测试查询不存在的争议"""
        resp = client.get("/api/v1/arbitrate/nonexistent_id")
        assert resp.status_code == 404

    def test_submit_missing_params(self, client):
        """测试提交争议缺少参数"""
        resp = client.post("/api/v1/arbitrate/submit", json={
            "reason": "测试"
        })
        assert resp.status_code == 400
