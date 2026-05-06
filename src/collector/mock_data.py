"""
模拟数据生成器

用于测试信用分计算，生成不同信用等级的模拟 Agent 数据。
"""

import hashlib
import random
import time
from typing import Dict, List

from ..credit.models import PerformanceRecord, TaskStatus


class MockDataGenerator:
    """
    模拟数据生成器

    生成三类 Agent 数据：
    - 高信用 Agent (AAA-AA): 高成功率、低超时、多交互
    - 中等信用 Agent (BBB-B): 中等表现
    - 低信用 Agent (CCC-C): 低成功率、高超时、争议多
    - 恶意 Agent: 严重违约、欺诈行为
    """

    # Agent 模板
    AGENT_PROFILES = {
        "high": {
            "success_rate": 0.95,
            "timeout_rate": 0.02,
            "dispute_rate": 0.01,
            "dispute_win_rate": 0.80,
            "avg_score": 0.85,
            "task_frequency": 5,  # 每天任务数
            "staked": 10.0,
            "counterparts": 50,
            "chains": 3,
        },
        "medium": {
            "success_rate": 0.75,
            "timeout_rate": 0.10,
            "dispute_rate": 0.05,
            "dispute_win_rate": 0.50,
            "avg_score": 0.60,
            "task_frequency": 2,
            "staked": 2.0,
            "counterparts": 15,
            "chains": 2,
        },
        "low": {
            "success_rate": 0.50,
            "timeout_rate": 0.25,
            "dispute_rate": 0.15,
            "dispute_win_rate": 0.20,
            "avg_score": 0.40,
            "task_frequency": 1,
            "staked": 0.5,
            "counterparts": 5,
            "chains": 1,
        },
        "malicious": {
            "success_rate": 0.20,
            "timeout_rate": 0.40,
            "dispute_rate": 0.50,
            "dispute_win_rate": 0.05,
            "avg_score": 0.20,
            "task_frequency": 3,
            "staked": 0.1,
            "counterparts": 3,
            "chains": 1,
        },
    }

    def __init__(self, seed: int = None):
        """
        初始化生成器

        Args:
            seed: 随机种子（可复现）
        """
        self.rng = random.Random(seed)
        self._agent_counter = 0

    def generate_agent_id(self, profile: str = "medium") -> str:
        """生成 Agent ID"""
        self._agent_counter += 1
        return f"agent_{profile}_{self._agent_counter:04d}"

    def generate_wallet(self, agent_id: str) -> str:
        """生成钱包地址"""
        h = hashlib.sha256(agent_id.encode()).hexdigest()
        return f"0x{h[:40]}"

    def generate_records(
        self,
        agent_id: str,
        profile: str = "medium",
        days: int = 90,
        min_records: int = 10,
    ) -> List[PerformanceRecord]:
        """
        生成履约记录

        Args:
            agent_id: Agent ID
            profile: 信用档案 (high/medium/low/malicious)
            days: 时间跨度（天）
            min_records: 最小记录数
        """
        config = self.AGENT_PROFILES.get(profile, self.AGENT_PROFILES["medium"])
        records = []

        now = int(time.time())
        total_tasks = max(min_records, days * config["task_frequency"])

        for i in range(total_tasks):
            # 时间分布：近期更密集
            days_ago = self.rng.uniform(0, days) * (1 - i / total_tasks)
            created_at = int(now - days_ago * 86400)

            # 决定任务结果
            status, success, score = self._generate_outcome(config)

            # 生成记录
            record = PerformanceRecord(
                record_id=f"rec_{agent_id}_{i:04d}",
                task_id=f"task_{agent_id}_{i:04d}",
                task_type=self.rng.choice(["escrow", "query", "compute"]),
                buyer_wallet=self._random_address(),
                seller_wallet=self.generate_wallet(agent_id),
                seller_agent_id=agent_id,
                chain=self.rng.choice(["bsc", "eth", "polygon"]) if config["chains"] > 1 else "bsc",
                amount=f"{self.rng.uniform(0.1, 10.0):.4f}",
                status=status,
                success=success,
                score=score,
                created_at=created_at,
                completed_at=created_at + self.rng.randint(100, 10000),
                response_time_ms=self.rng.randint(100, 5000),
                payment_tx=f"0x{self.rng.randbytes(32).hex()}",
                payment_amount=f"{self.rng.uniform(0.1, 10.0):.4f}",
                disputed=self.rng.random() < config["dispute_rate"],
                dispute_reason="",
                resolution=(self._random_resolution(config)
                            if self.rng.random() < config["dispute_rate"] else ""),
            )

            records.append(record)

        # 按时间排序
        records.sort(key=lambda r: r.created_at)
        return records

    def _generate_outcome(self, config: Dict) -> tuple:
        """生成任务结果"""
        r = self.rng.random()

        # 超时
        if r < config["timeout_rate"]:
            return TaskStatus.TIMEOUT, False, 0.0

        # 失败
        if r < config["timeout_rate"] + (1 - config["success_rate"]):
            return TaskStatus.FAILED, False, 0.0

        # 成功
        score = self.rng.uniform(
            config["avg_score"] - 0.2,
            min(1.0, config["avg_score"] + 0.2),
        )
        return TaskStatus.SETTLED, True, score

    def _random_resolution(self, config: Dict) -> str:
        """生成争议结果"""
        if self.rng.random() < config["dispute_win_rate"]:
            return "seller_win"
        return "buyer_win"

    def _random_address(self) -> str:
        """生成随机地址"""
        return f"0x{self.rng.randbytes(20).hex()}"

    def generate_agent_info(
        self,
        agent_id: str,
        profile: str = "medium",
    ) -> Dict:
        """
        生成 Agent 信息

        Args:
            agent_id: Agent ID
            profile: 信用档案
        """
        config = self.AGENT_PROFILES.get(profile, self.AGENT_PROFILES["medium"])

        return {
            "agent_id": agent_id,
            "wallet": self.generate_wallet(agent_id),
            "staked": config["staked"],
            "counterparts": config["counterparts"],
            "active_chains": ["bsc", "eth", "polygon"][:config["chains"]],
            "created_at": int(time.time()) - self.rng.randint(30, 365) * 86400,
        }

    def generate_credit_data(
        self,
        agent_id: str,
        profile: str = "medium",
    ) -> Dict:
        """
        生成信用货币数据

        Args:
            agent_id: Agent ID
            profile: 信用档案
        """
        config = self.AGENT_PROFILES.get(profile, self.AGENT_PROFILES["medium"])

        # 高信用 Agent 发行更多信用货币
        currency_count = int(config["success_rate"] * 10)
        accepted_count = int(config["success_rate"] * config["counterparts"])

        return {
            "currencies": [f"CR_{agent_id}_{i}" for i in range(currency_count)],
            "accepted_count": accepted_count,
            "accepted_by_agent": int(accepted_count * 0.5),
        }

    def generate_test_dataset(
        self,
        agents_per_profile: int = 3,
        days: int = 90,
    ) -> Dict:
        """
        生成完整测试数据集

        Args:
            agents_per_profile: 每类档案的 Agent 数
            days: 时间跨度

        Returns:
            {
                "agents": [agent_info, ...],
                "records": {agent_id: [records], ...},
                "credit_data": {agent_id: credit_data, ...},
            }
        """
        dataset = {
            "agents": [],
            "records": {},
            "credit_data": {},
        }

        for profile in ["high", "medium", "low", "malicious"]:
            for _ in range(agents_per_profile):
                agent_id = self.generate_agent_id(profile)
                agent_info = self.generate_agent_info(agent_id, profile)
                records = self.generate_records(agent_id, profile, days)
                credit_data = self.generate_credit_data(agent_id, profile)

                dataset["agents"].append(agent_info)
                dataset["records"][agent_id] = records
                dataset["credit_data"][agent_id] = credit_data

        return dataset
