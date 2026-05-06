"""
测试仲裁流程
"""

import pytest
from src.api_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestArbitration:
    """仲裁流程测试"""

    def test_submit_dispute(self, client):
        """测试提交争议"""
        # 创建托管
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]

        # 提交争议
        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "卖家未按约定交付"
        })
        assert dispute_resp.status_code == 200
        data = dispute_resp.get_json()
        assert data["state"] == "pending"
        assert data["escrow_id"] == escrow_id
        assert "dispute_id" in data

    def test_submit_dispute_with_evidence(self, client):
        """测试带证据提交争议"""
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]

        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "交付质量不达标",
            "evidence": {
                "description": "承诺交付 100 USDT，实际只收到 50 USDT",
                "tx_hash": "0xproof123"
            }
        })
        assert dispute_resp.status_code == 200
        data = dispute_resp.get_json()
        assert data["evidence"]["description"] == "承诺交付 100 USDT，实际只收到 50 USDT"

    def test_get_dispute(self, client):
        """测试查询争议"""
        # 创建争议
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "测试争议"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        # 查询争议
        get_resp = client.get(f"/api/v1/arbitrate/{dispute_id}")
        assert get_resp.status_code == 200
        data = get_resp.get_json()
        assert data["dispute_id"] == dispute_id
        assert data["state"] == "pending"

    def test_add_evidence(self, client):
        """测试添加证据"""
        # 创建争议
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "测试争议"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        # 添加证据
        evidence_resp = client.post(f"/api/v1/arbitrate/{dispute_id}/evidence", json={
            "description": "补充证据：链上交易记录",
            "attachments": ["https://bscscan.com/tx/0x..."]
        })
        assert evidence_resp.status_code == 200
        data = evidence_resp.get_json()
        assert "evidence_list" in data

    def test_get_arbitrators(self, client):
        """测试查询仲裁员"""
        # 创建争议
        create_resp = client.post("/api/v1/escrow/create", json={
            "buyer": "0x1111111111111111111111111111111111111111",
            "seller": "0x2222222222222222222222222222222222222222",
            "amount": 0.5
        })
        escrow_id = create_resp.get_json()["escrow_id"]
        dispute_resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": escrow_id,
            "reason": "测试争议"
        })
        dispute_id = dispute_resp.get_json()["dispute_id"]

        # 查询仲裁员
        arb_resp = client.get(f"/api/v1/arbitrate/{dispute_id}/arbitrators")
        assert arb_resp.status_code == 200
        data = arb_resp.get_json()
        assert "arbitrators" in data

    def test_dispute_not_found(self, client):
        """测试查询不存在的争议"""
        resp = client.get("/api/v1/arbitrate/nonexistent_id")
        assert resp.status_code == 404

    def test_submit_dispute_missing_params(self, client):
        """测试提交争议缺少参数"""
        resp = client.post("/api/v1/arbitrate/submit", json={
            "escrow_id": "test_escrow"
            # 缺少 reason
        })
        assert resp.status_code == 400

    def test_add_evidence_not_found(self, client):
        """测试给不存在的争议添加证据"""
        resp = client.post("/api/v1/arbitrate/nonexistent/evidence", json={
            "description": "测试证据"
        })
        assert resp.status_code == 404
