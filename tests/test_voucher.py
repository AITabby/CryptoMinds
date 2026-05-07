"""
Voucher API 测试
"""

from src.api_server import app
from src.store import UnifiedStore


class TestVoucherAPI:
    """Voucher API 测试"""

    def test_voucher_limit_preview(self):
        """测试额度预览"""
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/voucher/limit-preview",
                json={"agent_id": "agent_high_0001"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "credit_score" in data
            assert "credit_grade" in data
            assert "multiplier" in data
            assert "max_limit" in data

    def test_voucher_create(self):
        """测试创建 Voucher"""
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/voucher/create",
                json={
                    "issuer": "buyer_001",
                    "agent_id": "agent_high_0001",
                    "total_units": 100,
                    "unit_price": 0.01,
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["issuer"] == "buyer_001"
            assert data["agent_id"] == "agent_high_0001"
            assert data["total_units"] == 100
            assert data["units_used"] == 0
            assert data["status"] == "issued"
            assert "voucher_id" in data

    def test_voucher_get(self):
        """测试查询 Voucher"""
        with app.test_client() as client:
            # 先创建
            create_resp = client.post(
                "/api/v1/voucher/create",
                json={
                    "issuer": "buyer_002",
                    "agent_id": "agent_high_0001",
                    "total_units": 50,
                },
            )
            voucher_id = create_resp.get_json()["voucher_id"]

            # 再查询
            resp = client.get(f"/api/v1/voucher/{voucher_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["voucher_id"] == voucher_id

    def test_voucher_use(self):
        """测试使用 Voucher"""
        with app.test_client() as client:
            # 先创建
            create_resp = client.post(
                "/api/v1/voucher/create",
                json={
                    "issuer": "buyer_003",
                    "agent_id": "agent_high_0001",
                    "total_units": 100,
                },
            )
            voucher_id = create_resp.get_json()["voucher_id"]

            # 使用 10 单位
            resp = client.post(
                f"/api/v1/voucher/{voucher_id}/use",
                json={"units": 10},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["units_used"] == 10

            # 再使用 20 单位
            resp = client.post(
                f"/api/v1/voucher/{voucher_id}/use",
                json={"units": 20},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["units_used"] == 30

    def test_voucher_exhaust(self):
        """测试 Voucher 耗尽"""
        with app.test_client() as client:
            # 创建 10 单位的 voucher
            create_resp = client.post(
                "/api/v1/voucher/create",
                json={
                    "issuer": "buyer_004",
                    "agent_id": "agent_high_0001",
                    "total_units": 10,
                },
            )
            voucher_id = create_resp.get_json()["voucher_id"]

            # 使用全部
            resp = client.post(
                f"/api/v1/voucher/{voucher_id}/use",
                json={"units": 10},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "exhausted"

    def test_voucher_overuse(self):
        """测试超额使用"""
        with app.test_client() as client:
            # 创建 10 单位的 voucher
            create_resp = client.post(
                "/api/v1/voucher/create",
                json={
                    "issuer": "buyer_005",
                    "agent_id": "agent_high_0001",
                    "total_units": 10,
                },
            )
            voucher_id = create_resp.get_json()["voucher_id"]

            # 尝试使用 15 单位
            resp = client.post(
                f"/api/v1/voucher/{voucher_id}/use",
                json={"units": 15},
            )
            assert resp.status_code == 400
            assert "error" in resp.get_json()

    def test_voucher_list(self):
        """测试列表查询"""
        with app.test_client() as client:
            # 创建几个 voucher
            for i in range(3):
                client.post(
                    "/api/v1/voucher/create",
                    json={
                        "issuer": f"buyer_list_{i}",
                        "agent_id": "agent_high_0001",
                        "total_units": 50,
                    },
                )

            # 查询列表
            resp = client.get("/api/v1/voucher/list")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "vouchers" in data
            assert "total" in data
            assert data["total"] >= 3

    def test_voucher_list_by_agent(self):
        """测试按 Agent 查询"""
        with app.test_client() as client:
            resp = client.get("/api/v1/voucher/list?agent_id=agent_high_0001")
            assert resp.status_code == 200
            data = resp.get_json()
            for v in data["vouchers"]:
                assert v["agent_id"] == "agent_high_0001"


class TestVoucherStore:
    """Voucher 存储测试"""

    def test_create_voucher(self):
        """测试存储创建"""
        import uuid
        s = UnifiedStore()
        voucher = s.create_voucher(
            voucher_id=f"test_voucher_{uuid.uuid4().hex[:8]}",
            issuer="buyer_test",
            agent_id="agent_test",
            total_units=100,
            unit_price=0.01,
        )
        assert voucher["voucher_id"].startswith("test_voucher_")
        assert voucher["total_deposit"] == 1.0

    def test_get_voucher(self):
        """测试存储查询"""
        import uuid
        s = UnifiedStore()
        voucher_id = f"test_voucher_{uuid.uuid4().hex[:8]}"
        s.create_voucher(
            voucher_id=voucher_id,
            issuer="buyer_test",
            agent_id="agent_test",
            total_units=50,
            unit_price=0.02,
        )

        voucher = s.get_voucher(voucher_id)
        assert voucher is not None
        assert voucher["total_units"] == 50

    def test_use_voucher(self):
        """测试存储使用"""
        import uuid
        s = UnifiedStore()
        voucher_id = f"test_voucher_{uuid.uuid4().hex[:8]}"
        s.create_voucher(
            voucher_id=voucher_id,
            issuer="buyer_test",
            agent_id="agent_test",
            total_units=100,
            unit_price=0.01,
        )

        result = s.use_voucher(voucher_id, 30)
        assert result["units_used"] == 30
        assert result["status"] == "issued"

    def test_list_vouchers(self):
        """测试存储列表"""
        s = UnifiedStore()
        vouchers = s.list_vouchers(agent_id="agent_test")
        assert len(vouchers) >= 0
