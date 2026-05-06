"""
测试数据采集模块
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import unittest
from unittest.mock import patch, MagicMock


class TestMockDataGenerator(unittest.TestCase):
    """模拟数据生成器测试"""

    def test_generate_agent_id(self):
        """测试生成 Agent ID"""
        from src.collector.mock_data import MockDataGenerator

        gen = MockDataGenerator(seed=42)

        id1 = gen.generate_agent_id("high")
        id2 = gen.generate_agent_id("medium")

        self.assertIn("high", id1)
        self.assertIn("medium", id2)
        self.assertNotEqual(id1, id2)

    def test_generate_wallet(self):
        """测试生成钱包地址"""
        from src.collector.mock_data import MockDataGenerator

        gen = MockDataGenerator(seed=42)

        wallet = gen.generate_wallet("agent_test")
        self.assertTrue(wallet.startswith("0x"))
        self.assertEqual(len(wallet), 42)

    def test_generate_records_high_profile(self):
        """测试高信用档案记录生成"""
        from src.collector.mock_data import MockDataGenerator
        from src.credit.models import TaskStatus

        gen = MockDataGenerator(seed=42)

        records = gen.generate_records("agent_high", "high", days=30)

        # 高信用档案应该有高成功率
        settled = sum(1 for r in records if r.status == TaskStatus.SETTLED)
        success_rate = settled / len(records)

        self.assertGreater(success_rate, 0.8)  # 80% 以上成功率

    def test_generate_records_malicious_profile(self):
        """测试恶意档案记录生成"""
        from src.collector.mock_data import MockDataGenerator
        from src.credit.models import TaskStatus

        gen = MockDataGenerator(seed=42)

        records = gen.generate_records("agent_malicious", "malicious", days=30)

        # 恶意档案应该有低成功率
        settled = sum(1 for r in records if r.status == TaskStatus.SETTLED)
        success_rate = settled / len(records)

        self.assertLess(success_rate, 0.3)  # 30% 以下成功率

    def test_generate_agent_info(self):
        """测试生成 Agent 信息"""
        from src.collector.mock_data import MockDataGenerator

        gen = MockDataGenerator(seed=42)

        info_high = gen.generate_agent_info("agent_high", "high")
        info_low = gen.generate_agent_info("agent_low", "low")

        # 高信用档案应该有更多质押
        self.assertGreater(info_high["staked"], info_low["staked"])
        # 高信用档案应该有更多对手方
        self.assertGreater(info_high["counterparts"], info_low["counterparts"])

    def test_generate_credit_data(self):
        """测试生成信用货币数据"""
        from src.collector.mock_data import MockDataGenerator

        gen = MockDataGenerator(seed=42)

        data = gen.generate_credit_data("agent_high", "high")

        self.assertIn("currencies", data)
        self.assertIn("accepted_count", data)

    def test_generate_test_dataset(self):
        """测试生成完整测试数据集"""
        from src.collector.mock_data import MockDataGenerator

        gen = MockDataGenerator(seed=42)

        dataset = gen.generate_test_dataset(agents_per_profile=2, days=30)

        self.assertEqual(len(dataset["agents"]), 8)  # 4 profiles * 2
        self.assertEqual(len(dataset["records"]), 8)
        self.assertEqual(len(dataset["credit_data"]), 8)


class TestChainListener(unittest.TestCase):
    """链监听器测试"""

    def test_mock_mode(self):
        """测试模拟模式"""
        from src.collector.chain_listener import ChainListener

        listener = ChainListener(mock_mode=True)
        self.assertTrue(listener.mock_mode)

        # 连接应该成功
        self.assertTrue(listener.connect())

        # 获取事件应该返回空列表
        events = listener.fetch_events()
        self.assertEqual(len(events), 0)

    def test_event_types(self):
        """测试事件类型"""
        from src.collector.chain_listener import EventType

        self.assertEqual(EventType.ESCROW_CREATED.value, "EscrowCreated")
        self.assertEqual(EventType.ESCROW_RELEASED.value, "EscrowReleased")
        self.assertEqual(EventType.DISPUTE_RAISED.value, "DisputeRaised")

    def test_chain_event_dataclass(self):
        """测试链事件数据类"""
        from src.collector.chain_listener import ChainEvent, EventType

        event = ChainEvent(
            event_type=EventType.ESCROW_CREATED,
            tx_hash="0xabc123",
            block_number=1000,
            timestamp=1715040000,
            escrow_id="escrow_001",
            buyer="0x1111",
            seller="0x2222",
            amount="1.0",
        )

        self.assertEqual(event.event_type, EventType.ESCROW_CREATED)
        self.assertEqual(event.tx_hash, "0xabc123")


class TestPerformanceSyncer(unittest.TestCase):
    """履约记录同步器测试"""

    def test_syncer_initialization(self):
        """测试同步器初始化"""
        from src.collector.performance_sync import PerformanceSyncer
        from src.collector.chain_listener import ChainListener

        listener = ChainListener(mock_mode=True)
        syncer = PerformanceSyncer(listener=listener)

        self.assertIsNotNone(syncer.listener)
        self.assertIsNotNone(syncer.store)

    def test_get_records_for_agent_empty(self):
        """测试获取空记录"""
        from src.collector.performance_sync import PerformanceSyncer
        from src.collector.chain_listener import ChainListener

        # 使用临时数据库
        import tempfile
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = temp_db.name
        temp_db.close()

        try:
            from src.store import UnifiedStore
            store = UnifiedStore(db_path=db_path)

            listener = ChainListener(mock_mode=True)
            syncer = PerformanceSyncer(listener=listener, store=store)

            records = syncer.get_records_for_agent("nonexistent")
            self.assertEqual(len(records), 0)
        finally:
            import os
            try:
                os.unlink(db_path)
            except:
                pass


if __name__ == "__main__":
    unittest.main()
