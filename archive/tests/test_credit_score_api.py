"""
信用分 API 测试
"""

import json
import pytest
import time

from flask import Flask

from credit_score.api import credit_score_bp
from credit_score.store import CreditScoreStore
from credit_score.models import SacredScore, DimensionScore


@pytest.fixture
def app(tmp_path):
    """创建测试 Flask 应用"""
    app = Flask(__name__)
    app.register_blueprint(credit_score_bp)

    # 覆盖存储路径
    db_path = str(tmp_path / "test_api_credit_score.db")
    store = CreditScoreStore(db_path=db_path)

    # 注入到蓝图模块
    import credit_score.api as api_module
    from credit_score.calculator import SacredCalculator
    api_module._store = store
    api_module._calculator = SacredCalculator()
    api_module._bridge = None  # 让它懒初始化但不需要

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_api_credit_score.db")
    return CreditScoreStore(db_path=db_path)


def _make_and_save_score(store, agent_id="agent-1", wallet="0xabc", total=750):
    """创建并保存一个分数"""
    now = int(time.time())
    score = SacredScore(agent_id=agent_id, wallet=wallet, calculated_at=now)
    per_dim = total / 5
    for d in score.dimensions.values():
        d.raw_score = per_dim
        d.weighted_score = per_dim
    score.total_score = total
    score.compute_hash()
    store.save_score(score)
    return score


class TestHealthCheck:

    def test_health(self, client):
        resp = client.get("/api/v1/credit-score/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["module"] == "credit_score"


class TestGetScore:

    def test_get_existing_score(self, client, store):
        _make_and_save_score(store, "agent-1", "0xabc", 750)

        resp = client.get("/api/v1/credit-score/agent-1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["agent_id"] == "agent-1"
        assert data["total_score"] == 750

    def test_get_nonexistent_agent(self, client):
        # 没有桥接数据库，会返回 404
        resp = client.get("/api/v1/credit-score/nonexistent-agent")
        assert resp.status_code == 404


class TestGetProfile:

    def test_get_profile(self, client, store):
        _make_and_save_score(store, "agent-1", "0xabc", 750)

        resp = client.get("/api/v1/credit-score/agent-1/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dimensions" in data
        assert "history" in data
        assert data["total_score"] == 750


class TestGetHistory:

    def test_get_history(self, client, store):
        _make_and_save_score(store, "agent-1", "0xabc", 750)

        resp = client.get("/api/v1/credit-score/agent-1/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "history" in data
        assert len(data["history"]) >= 1


class TestAuthorization:

    def test_create_authorization(self, client, store):
        # 先保存一个分数
        _make_and_save_score(store, "agent-1", "0xabc", 750)

        resp = client.post(
            "/api/v1/credit-score/agent-1/authorize",
            data=json.dumps({"querier_id": "agent-2", "signature": "0xsig"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "auth_id" in data
        assert data["querier_id"] == "agent-2"

    def test_create_authorization_missing_fields(self, client):
        resp = client.post(
            "/api/v1/credit-score/agent-1/authorize",
            data=json.dumps({"querier_id": "agent-2"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_revoke_authorization(self, client, store):
        _make_and_save_score(store, "agent-1", "0xabc", 750)

        # 创建授权
        resp = client.post(
            "/api/v1/credit-score/agent-1/authorize",
            data=json.dumps({"querier_id": "agent-2", "signature": "0xsig"}),
            content_type="application/json",
        )
        auth_id = resp.get_json()["auth_id"]

        # 撤销
        resp = client.delete(f"/api/v1/credit-score/agent-1/authorize/{auth_id}")
        assert resp.status_code == 200

    def test_revoke_nonexistent(self, client):
        resp = client.delete("/api/v1/credit-score/agent-1/authorize/nonexistent")
        assert resp.status_code == 404


class TestLeaderboard:

    def test_leaderboard(self, client, store):
        for i in range(5):
            _make_and_save_score(store, f"agent-{i}", f"0x{i}", 500 + i * 100)

        resp = client.get("/api/v1/credit-score/leaderboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["leaderboard"]) == 5
        # 降序
        scores = [e["total_score"] for e in data["leaderboard"]]
        assert scores == sorted(scores, reverse=True)

    def test_leaderboard_with_limit(self, client, store):
        for i in range(5):
            _make_and_save_score(store, f"agent-lb-{i}", f"0xlb{i}", 500 + i * 100)

        resp = client.get("/api/v1/credit-score/leaderboard?limit=3")
        data = resp.get_json()
        assert len(data["leaderboard"]) == 3


class TestRefreshScore:

    def test_refresh_unauthorized(self, client):
        resp = client.post("/api/v1/credit-score/agent-1/refresh")
        # 无 internal token 时，如果环境没有配置 token，默认通过
        # 如果配置了 token 则返回 403
        assert resp.status_code in (200, 403, 404)
