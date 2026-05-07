"""
Collector 模拟数据测试
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector.mock_data import MockDataGenerator
from src.credit.models import TaskStatus


class TestMockDataGenerator:
    """模拟数据生成器测试"""

    def test_create_generator(self):
        """测试创建生成器"""
        gen = MockDataGenerator()
        assert gen is not None

    def test_create_generator_with_seed(self):
        """测试带种子的生成器"""
        gen = MockDataGenerator(seed=42)
        assert gen is not None

    def test_generate_agent_id(self):
        """测试生成 Agent ID"""
        gen = MockDataGenerator()

        for profile in ["high", "medium", "low", "malicious"]:
            agent_id = gen.generate_agent_id(profile)
            assert agent_id.startswith("agent_")

    def test_generate_wallet(self):
        """测试生成钱包地址"""
        gen = MockDataGenerator()
        wallet = gen.generate_wallet("agent_test")
        assert wallet.startswith("0x")
        assert len(wallet) == 42

    def test_generate_records(self):
        """测试生成记录"""
        gen = MockDataGenerator()
        records = gen.generate_records(
            agent_id="agent_high_001",
            profile="high",
            days=30,
        )

        assert len(records) > 0
        assert all(r.seller_agent_id == "agent_high_001" for r in records)

    def test_generate_records_different_profiles(self):
        """测试不同 profile 生成不同记录"""
        gen = MockDataGenerator()

        high_records = gen.generate_records(agent_id="high", profile="high", days=30)
        low_records = gen.generate_records(agent_id="low", profile="low", days=30)

        # 高信用 Agent 应该有更多成功记录
        high_success = sum(1 for r in high_records if r.success)
        low_success = sum(1 for r in low_records if r.success)

        # 只验证记录存在
        assert len(high_records) > 0
        assert len(low_records) > 0

    def test_generate_agent_info(self):
        """测试生成 Agent 信息"""
        gen = MockDataGenerator()
        info = gen.generate_agent_info(
            agent_id="test_agent",
            profile="high",
        )

        assert "staked" in info
        assert "active_chains" in info
        assert "counterparts" in info

    def test_generate_credit_data(self):
        """测试生成信用数据"""
        gen = MockDataGenerator()
        data = gen.generate_credit_data(
            agent_id="test_agent",
            profile="high",
        )

        assert "currencies" in data
        assert "accepted_count" in data

    def test_generate_test_dataset(self):
        """测试生成测试数据集"""
        gen = MockDataGenerator()
        dataset = gen.generate_test_dataset(
            agents_per_profile=2,
            days=7,
        )

        assert "agents" in dataset
        assert "records" in dataset
        # 4 profiles * 2 agents per profile = 8 agents
        assert len(dataset["agents"]) == 8

    def test_agent_profiles_defined(self):
        """测试 Agent 配置已定义"""
        assert "high" in MockDataGenerator.AGENT_PROFILES
        assert "medium" in MockDataGenerator.AGENT_PROFILES
        assert "low" in MockDataGenerator.AGENT_PROFILES
        assert "malicious" in MockDataGenerator.AGENT_PROFILES

    def test_high_profile_has_high_success_rate(self):
        """测试高信用配置有高成功率"""
        profile = MockDataGenerator.AGENT_PROFILES["high"]
        assert profile["success_rate"] > 0.9

    def test_malicious_profile_has_low_success_rate(self):
        """测试恶意配置有低成功率"""
        profile = MockDataGenerator.AGENT_PROFILES["malicious"]
        assert profile["success_rate"] < 0.5
