"""
模拟数据生成器 — 200 Agent / 3000 交易 / 3 链 / 180 天

生成模拟数据写入现有系统 SQLite（供 bridge 读取），
同时触发信用分计算写入信用分数据库。
"""

import hashlib
import json
import random
import sqlite3
import time
from decimal import Decimal
from typing import Dict, List, Optional

from .calculator import SacredCalculator
from .bridge import CreditScoreBridge
from .store import CreditScoreStore
from .config import DEFAULT_DB_PATH


class CreditScoreDataGenerator:
    """模拟数据生成器"""

    CHAINS = ["bsc", "solana", "polygon"]
    TASK_TYPES = ["token_delivery", "data_delivery", "swap_execution"]
    PERIOD_DAYS = 180

    # Agent 档位配置
    TIERS = [
        {"name": "顶级", "pct": 0.10, "stake_range": (50, 200), "success_rate": (0.95, 0.99), "dispute_rate": (0.01, 0.03), "task_range": (30, 50)},
        {"name": "优秀", "pct": 0.20, "stake_range": (10, 50), "success_rate": (0.88, 0.95), "dispute_rate": (0.03, 0.06), "task_range": (15, 30)},
        {"name": "一般", "pct": 0.30, "stake_range": (2, 10), "success_rate": (0.75, 0.88), "dispute_rate": (0.06, 0.12), "task_range": (8, 20)},
        {"name": "新手", "pct": 0.25, "stake_range": (0.5, 2), "success_rate": (0.60, 0.80), "dispute_rate": (0.03, 0.08), "task_range": (2, 8)},
        {"name": "劣迹", "pct": 0.15, "stake_range": (0.1, 1), "success_rate": (0.30, 0.60), "dispute_rate": (0.15, 0.30), "task_range": (3, 10)},
    ]

    def __init__(self, db_path: str = None, credit_db_path: str = None, seed: int = 42):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._credit_db_path = credit_db_path or DEFAULT_DB_PATH
        self._rng = random.Random(seed)
        self._agents = []
        self._records = []
        self._stats = {}

    def generate(self) -> Dict:
        """生成全部模拟数据，返回统计摘要"""
        print("[generator] Starting data generation...")

        # 1. 初始化数据库表
        self._init_db()

        # 2. 生成 Agent
        self._agents = self._generate_agents()
        print(f"[generator] Generated {len(self._agents)} agents")

        # 3. 生成交易记录
        self._records = self._generate_records()
        print(f"[generator] Generated {len(self._records)} records")

        # 4. 生成信用货币和接受关系
        self._generate_credit_relations()

        # 5. 写入数据库
        self._write_to_db()
        print(f"[generator] Written to {self._db_path}")

        # 6. 计算信用分
        self._calculate_all_scores()
        print(f"[generator] Credit scores calculated")

        return self._stats

    def _init_db(self):
        """确保数据库表存在（模块自建，不依赖主项目）"""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_records (
                    record_id TEXT PRIMARY KEY,
                    task_id TEXT DEFAULT '',
                    task_type TEXT DEFAULT '',
                    buyer_wallet TEXT DEFAULT '',
                    seller_wallet TEXT DEFAULT '',
                    seller_agent_id TEXT DEFAULT '',
                    chain TEXT DEFAULT '',
                    amount TEXT DEFAULT '0',
                    status TEXT DEFAULT 'pending',
                    success INTEGER DEFAULT 0,
                    score REAL DEFAULT 0.0,
                    created_at INTEGER DEFAULT 0,
                    completed_at INTEGER DEFAULT 0,
                    response_time_ms INTEGER DEFAULT 0,
                    payment_tx TEXT DEFAULT '',
                    payment_amount TEXT DEFAULT '0',
                    evidence TEXT DEFAULT '{}',
                    disputed INTEGER DEFAULT 0,
                    dispute_reason TEXT DEFAULT '',
                    resolution TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credit_currencies (
                    currency_id TEXT PRIMARY KEY,
                    issuer_agent_id TEXT DEFAULT '',
                    issuer_wallet TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    symbol TEXT DEFAULT '',
                    max_supply TEXT DEFAULT '0',
                    backed_by TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    created_at INTEGER DEFAULT 0,
                    accepted_by TEXT DEFAULT '[]'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_seller_wallet ON performance_records(seller_wallet)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_seller_agent_id ON performance_records(seller_agent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_buyer_wallet ON performance_records(buyer_wallet)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_issuer ON credit_currencies(issuer_agent_id)")
            conn.commit()
        finally:
            conn.close()

    def _generate_agents(self) -> List[Dict]:
        """生成 200 个 Agent"""
        agents = []
        agent_id = 0

        for tier in self.TIERS:
            count = int(200 * tier["pct"])
            for i in range(count):
                agent_id += 1
                wallet = f"0x{hashlib.sha256(f'agent-{agent_id}'.encode()).hexdigest()[:40]}"

                # 分配链
                chain_roll = self._rng.random()
                if chain_roll < 0.30:
                    chains = [self._rng.choice(self.CHAINS)]
                elif chain_roll < 0.80:
                    chains = self._rng.sample(self.CHAINS, 2)
                else:
                    chains = self.CHAINS[:]

                # 质押量
                staked = self._rng.uniform(*tier["stake_range"])

                agents.append({
                    "agent_id": f"sim-agent-{agent_id:03d}",
                    "wallet": wallet,
                    "tier": tier["name"],
                    "chains": chains,
                    "staked": round(staked, 2),
                    "success_rate_range": tier["success_rate"],
                    "dispute_rate_range": tier["dispute_rate"],
                    "task_count_range": tier["task_range"],
                })

        return agents

    def _generate_records(self) -> List[Dict]:
        """按 Agent 档位生成交易记录"""
        records = []
        now = int(time.time())
        start_ts = now - self.PERIOD_DAYS * 86400

        for agent in self._agents:
            task_count = self._rng.randint(*agent["task_count_range"])
            success_rate = self._rng.uniform(*agent["success_rate_range"])
            dispute_rate = self._rng.uniform(*agent["dispute_rate_range"])

            for j in range(task_count):
                # 时间分布：近期稍密
                days_ago = self._rng.expovariate(1 / 60)  # 平均60天前
                days_ago = min(days_ago, self.PERIOD_DAYS - 1)
                created_at = now - int(days_ago * 86400)

                # 选择链
                chain = self._rng.choice(agent["chains"])

                # 选择任务类型
                task_type = self._rng.choice(self.TASK_TYPES)

                # 金额：幂律分布
                amount = round(0.01 * (10 ** self._rng.uniform(0, 2.5)), 4)

                # 结果
                is_success = self._rng.random() < success_rate
                is_disputed = not is_success and self._rng.random() < dispute_rate

                if is_success:
                    status = "settled"
                    score = self._rng.uniform(0.7, 1.0)
                elif is_disputed:
                    status = "disputed"
                    score = self._rng.uniform(0.2, 0.6)
                    # 争议结果
                    resolution = self._rng.choice(["buyer_win", "seller_win", "split"])
                else:
                    status = self._rng.choice(["failed", "timeout"])
                    score = 0.0
                    resolution = ""

                # 买家
                buyer_seed = f"buyer-{agent['agent_id']}-{j}"
                buyer_wallet = f"0x{hashlib.sha256(buyer_seed.encode()).hexdigest()[:40]}"

                record_id = hashlib.sha256(f"record-{agent['wallet']}-{j}-{created_at}".encode()).hexdigest()[:32]

                records.append({
                    "record_id": record_id,
                    "task_id": f"task-{record_id[:8]}",
                    "task_type": task_type,
                    "buyer_wallet": buyer_wallet,
                    "seller_wallet": agent["wallet"],
                    "seller_agent_id": agent["agent_id"],
                    "chain": chain,
                    "amount": str(amount),
                    "status": status,
                    "success": 1 if is_success else 0,
                    "score": score,
                    "created_at": created_at,
                    "completed_at": created_at + self._rng.randint(100, 5000),
                    "response_time_ms": self._rng.randint(200, 10000),
                    "payment_tx": f"0xtx{hashlib.sha256(f'tx-{record_id}'.encode()).hexdigest()[:20]}" if is_success else "",
                    "payment_amount": str(amount) if is_success else "0",
                    "evidence": "{}",
                    "disputed": 1 if is_disputed else 0,
                    "dispute_reason": "quality issue" if is_disputed else "",
                    "resolution": resolution if is_disputed else "",
                })

        return records

    def _generate_credit_relations(self):
        """生成信用货币发行和接受关系"""
        # 顶级和优秀 Agent 发行货币
        for agent in self._agents:
            if agent["tier"] == "顶级":
                agent["issued_currencies"] = self._rng.randint(3, 6)
            elif agent["tier"] == "优秀":
                agent["issued_currencies"] = self._rng.randint(1, 3)
            else:
                agent["issued_currencies"] = 0

    def _write_to_db(self):
        """写入现有系统 SQLite"""
        conn = sqlite3.connect(self._db_path)
        try:
            # 清空旧数据
            conn.execute("DELETE FROM performance_records WHERE seller_agent_id LIKE 'sim-agent-%'")

            # 写入交易记录
            for r in self._records:
                conn.execute(
                    """INSERT OR IGNORE INTO performance_records
                       (record_id, task_id, task_type, buyer_wallet, seller_wallet,
                        seller_agent_id, chain, amount, status, success, score,
                        created_at, completed_at, response_time_ms,
                        payment_tx, payment_amount, evidence,
                        disputed, dispute_reason, resolution)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["record_id"], r["task_id"], r["task_type"],
                        r["buyer_wallet"], r["seller_wallet"], r["seller_agent_id"],
                        r["chain"], r["amount"], r["status"], r["success"], r["score"],
                        r["created_at"], r["completed_at"], r["response_time_ms"],
                        r["payment_tx"], r["payment_amount"], r["evidence"],
                        r["disputed"], r["dispute_reason"], r["resolution"],
                    ),
                )

            # 写入信用货币
            conn.execute("DELETE FROM credit_currencies WHERE issuer_agent_id LIKE 'sim-agent-%'")
            currency_id = 0
            for agent in self._agents:
                for i in range(agent.get("issued_currencies", 0)):
                    currency_id += 1
                    cur_id = f"sim-cur-{currency_id:03d}"
                    # 被多少 Agent 接受
                    accepted_count = self._rng.randint(1, 20)
                    accepted_agents = [a["agent_id"] for a in self._rng.sample(self._agents, min(accepted_count, len(self._agents)))]

                    conn.execute(
                        """INSERT OR IGNORE INTO credit_currencies
                           (currency_id, issuer_agent_id, issuer_wallet, name, symbol,
                            max_supply, backed_by, active, created_at, accepted_by)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            cur_id, agent["agent_id"], agent["wallet"],
                            f"SimToken{currency_id}", f"ST{currency_id}",
                            "10000", "bsc", 1,
                            agent.get("created_at", int(time.time())),
                            json.dumps(accepted_agents),
                        ),
                    )

            conn.commit()
        finally:
            conn.close()

    def _calculate_all_scores(self):
        """为所有 Agent 计算信用分"""
        bridge = CreditScoreBridge(db_path=self._db_path)
        store = CreditScoreStore(db_path=self._credit_db_path)
        calculator = SacredCalculator()

        grade_distribution = {}

        for agent in self._agents:
            try:
                records_dict = bridge.get_records_by_seller(agent["wallet"])
                from .models import PerformanceRecord
                records = [PerformanceRecord.from_dict(r) for r in records_dict]

                credit_acceptance = bridge.get_credit_acceptance(agent["agent_id"])
                accepted_by_agent = bridge.get_accepted_by_agent(agent["agent_id"])
                currencies = bridge.get_credit_currencies()

                chains = bridge.get_chain_coverage(agent["wallet"])
                counterparts = bridge.get_unique_counterparts(agent["wallet"])

                credit_data = {
                    "accepted_count": credit_acceptance.get("accepted_count", 0),
                    "accepted_by_agent": accepted_by_agent,
                    "currencies": currencies,
                }

                agent_info = {
                    "staked": agent["staked"],
                    "active_chains": chains,
                    "counterparts": counterparts,
                }

                score = calculator.calculate(
                    agent_id=agent["agent_id"],
                    wallet=agent["wallet"],
                    records=records,
                    credit_data=credit_data,
                    agent_info=agent_info,
                )

                store.save_score(score)

                grade = score.grade
                grade_distribution[grade] = grade_distribution.get(grade, 0) + 1

            except Exception as e:
                print(f"[generator] Error calculating score for {agent['agent_id']}: {e}")

        self._stats = {
            "total_agents": len(self._agents),
            "total_records": len(self._records),
            "chains": self.CHAINS,
            "period_days": self.PERIOD_DAYS,
            "grade_distribution": grade_distribution,
        }

    def get_statistics(self) -> Dict:
        """返回生成数据的统计摘要"""
        return self._stats


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate simulated credit score data")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to simulation database")
    parser.add_argument("--credit-db", default=DEFAULT_DB_PATH, help="Path to credit_score.db")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    generator = CreditScoreDataGenerator(
        db_path=args.db,
        credit_db_path=args.credit_db,
        seed=args.seed,
    )

    stats = generator.generate()

    print("\n=== Generation Statistics ===")
    print(f"Total agents: {stats['total_agents']}")
    print(f"Total records: {stats['total_records']}")
    print(f"Chains: {stats['chains']}")
    print(f"Period: {stats['period_days']} days")
    print(f"\nGrade Distribution:")
    for grade in ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C"]:
        count = stats.get("grade_distribution", {}).get(grade, 0)
        if count > 0:
            print(f"  {grade}: {count}")


if __name__ == "__main__":
    main()
