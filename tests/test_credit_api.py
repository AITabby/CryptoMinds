"""
测试信用分 API
"""

import sys
import os
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


class TestCreditAPI(unittest.TestCase):
    """信用分 API 测试"""

    def setUp(self):
        """设置测试环境"""
        os.environ["CRYPTOMINDS_REQUIRE_AUTH"] = "false"
        os.environ["CRYPTOMINDS_DEBUG"] = "true"

        # 使用临时数据库
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        os.environ["CRYPTOMINDS_DB_PATH"] = self.db_path

        from src.api_server import app
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        """清理"""
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_credit_score_with_records(self):
        """测试有履约记录时的信用分计算"""
        resp = self.client.get("/api/v1/credit/0xtest_agent_new")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        # 冷启动分数应该是 250
        self.assertEqual(data["total_score"], 250)
        self.assertEqual(data["grade"], "CCC")

    def test_credit_history(self):
        """测试信用分历史"""
        resp = self.client.get("/api/v1/credit/0x1234/history")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("history", data)

    def test_credit_ranking(self):
        """测试信用分排行榜"""
        resp = self.client.get("/api/v1/credit/ranking")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("ranking", data)

    def test_credit_refresh(self):
        """测试刷新信用分"""
        resp = self.client.post(
            "/api/v1/credit/0xtest_refresh/refresh",
            json={
                "agent_id": "0xtest_refresh",
                "wallet": "0xtest_refresh",
                "records": [],
                "credit_data": {"accepted_count": 5},
                "agent_info": {"staked": 10.0, "counterparts": 20},
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("total_score", data)


class TestColdStart(unittest.TestCase):
    """冷启动测试"""

    def test_cold_start_score_dimensions(self):
        """测试冷启动分数各维度"""
        from src.credit.api import _cold_start_score

        score = _cold_start_score("0xtest")

        # 总分 250
        self.assertEqual(score.total_score, 250)
        # 等级 CCC
        self.assertEqual(score.grade, "CCC")
        # 每个维度 50 分
        self.assertEqual(score.stability.weighted_score, 50)
        self.assertEqual(score.activity.weighted_score, 50)
        self.assertEqual(score.creditworthiness.weighted_score, 50)
        self.assertEqual(score.reliability.weighted_score, 50)
        self.assertEqual(score.ecosystem.weighted_score, 50)


if __name__ == "__main__":
    unittest.main()
