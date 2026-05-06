"""
测试统一存储层
"""

import sys
import os
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


class TestUnifiedStore(unittest.TestCase):
    """统一存储测试"""

    def setUp(self):
        """每个测试使用临时数据库"""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        from src.store import UnifiedStore
        self.store = UnifiedStore(db_path=self.db_path)

    def tearDown(self):
        """清理临时数据库"""
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_create_and_get_escrow(self):
        """测试创建和获取托管"""
        escrow = self.store.create_escrow(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=1.0,
            token="BNB",
        )

        self.assertIn("escrow_id", escrow)
        self.assertEqual(escrow["status"], "pending")

        # 获取
        retrieved = self.store.get_escrow(escrow["escrow_id"])
        self.assertEqual(retrieved["buyer"], escrow["buyer"])
        self.assertEqual(retrieved["seller"], escrow["seller"])

    def test_update_escrow_status(self):
        """测试更新托管状态"""
        escrow = self.store.create_escrow(
            buyer="0x1111",
            seller="0x2222",
            amount=1.0,
        )

        # 更新为 funded
        updated = self.store.update_escrow_status(
            escrow["escrow_id"],
            "funded",
            fund_tx="0xabc123",
            funded_at=1715040000,
        )

        self.assertEqual(updated["status"], "funded")
        self.assertEqual(updated["fund_tx"], "0xabc123")

    def test_list_escrows_by_status(self):
        """测试按状态列出托管"""
        # 创建多个托管
        self.store.create_escrow("0x1111", "0x2222", 1.0)
        escrow2 = self.store.create_escrow("0x3333", "0x4444", 2.0)

        # 更新一个为 funded
        self.store.update_escrow_status(escrow2["escrow_id"], "funded")

        # 列出 pending 状态
        pending = self.store.list_escrows_by_status("pending")
        funded = self.store.list_escrows_by_status("funded")

        self.assertEqual(len(pending), 1)
        self.assertEqual(len(funded), 1)

    def test_create_and_get_dispute(self):
        """测试创建和获取争议"""
        escrow = self.store.create_escrow("0x1111", "0x2222", 1.0)

        dispute = self.store.create_dispute(
            escrow_id=escrow["escrow_id"],
            reason="商品与描述不符",
        )

        self.assertIn("dispute_id", dispute)
        self.assertEqual(dispute["status"], "pending")

        # 获取
        retrieved = self.store.get_dispute(dispute["dispute_id"])
        self.assertEqual(retrieved["reason"], "商品与描述不符")

    def test_add_dispute_evidence(self):
        """测试添加证据"""
        escrow = self.store.create_escrow("0x1111", "0x2222", 1.0)
        dispute = self.store.create_dispute(escrow["escrow_id"], "test")

        updated = self.store.add_dispute_evidence(
            dispute["dispute_id"],
            {"type": "image", "url": "http://example.com/img.png"},
        )

        self.assertTrue(len(updated["evidence_list"]) > 0)

    def test_resolve_dispute(self):
        """测试解决争议"""
        escrow = self.store.create_escrow("0x1111", "0x2222", 1.0)
        dispute = self.store.create_dispute(escrow["escrow_id"], "test")

        resolved = self.store.resolve_dispute(
            dispute["dispute_id"],
            result="seller_wins",
            reason="卖家提供了有效证明",
        )

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["result"], "seller_wins")

    def test_save_and_get_performance_record(self):
        """测试保存和获取履约记录"""
        from src.credit.models import PerformanceRecord, TaskStatus

        record = PerformanceRecord(
            record_id="perf_test_001",
            task_id="task_001",
            task_type="escrow",
            buyer_wallet="0x1111",
            seller_wallet="0x2222",
            seller_agent_id="agent_001",
            chain="bsc",
            amount="1.0",
            status=TaskStatus.SETTLED,
            success=True,
            score=0.8,
            created_at=1715040000,
            completed_at=1715040100,
            response_time_ms=1000,
        )

        self.store.save_performance_record(record)

        # 获取
        records = self.store.get_performance_records(agent_id="agent_001")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_id, "perf_test_001")

    def test_get_performance_records_by_wallet(self):
        """测试按钱包获取履约记录"""
        from src.credit.models import PerformanceRecord, TaskStatus

        # 创建两条记录
        record1 = PerformanceRecord(
            record_id="perf_001",
            task_id="task_001",
            task_type="escrow",
            buyer_wallet="0x1111",
            seller_wallet="0x2222",
            seller_agent_id="agent_001",
            chain="bsc",
            amount="1.0",
            status=TaskStatus.SETTLED,
            success=True,
            created_at=1715040000,
        )

        record2 = PerformanceRecord(
            record_id="perf_002",
            task_id="task_002",
            task_type="escrow",
            buyer_wallet="0x3333",
            seller_wallet="0x2222",
            seller_agent_id="agent_002",
            chain="bsc",
            amount="2.0",
            status=TaskStatus.SETTLED,
            success=True,
            created_at=1715040100,
        )

        self.store.save_performance_record(record1)
        self.store.save_performance_record(record2)

        # 查询 seller_wallet
        records = self.store.get_performance_records(wallet="0x2222")
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
