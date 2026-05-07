#!/usr/bin/env python3
"""
数据生成脚本

生成模拟 Agent 和履约记录，计算信用分，写入数据库。
运行: python scripts/generate_data.py
"""

import sys
import os

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 切换到项目根目录，确保相对路径正确
os.chdir(PROJECT_ROOT)

from src.collector.mock_data import MockDataGenerator
from src.credit import SacredCalculator, CreditScoreStore
from src.credit.models import PerformanceRecord, TaskStatus


def main():
    print("=" * 50)
    print("CryptoMinds 数据生成器")
    print("=" * 50)

    # 初始化
    generator = MockDataGenerator(seed=42)  # 固定种子，可复现
    calculator = SacredCalculator()
    store = CreditScoreStore()

    # 配置：每类 Agent 数量
    agents_per_profile = 10  # high/medium/low/malicious 各 10 个 = 40 个

    print(f"\n📊 生成配置:")
    print(f"   - 每类 Agent 数量: {agents_per_profile}")
    print(f"   - 总 Agent 数: {agents_per_profile * 4}")
    print(f"   - 时间跨度: 90 天")

    # 生成数据集
    print("\n⏳ 正在生成模拟数据...")
    dataset = generator.generate_test_dataset(
        agents_per_profile=agents_per_profile,
        days=90,
    )

    print(f"   ✓ 生成 {len(dataset['agents'])} 个 Agent")

    # 统计
    total_records = sum(len(r) for r in dataset['records'].values())
    print(f"   ✓ 生成 {total_records} 条履约记录")

    # 写入数据库
    print("\n⏳ 正在写入数据库...")

    success_count = 0
    error_count = 0

    for i, agent_info in enumerate(dataset['agents']):
        agent_id = agent_info['agent_id']
        records = dataset['records'][agent_id]
        credit_data = dataset['credit_data'][agent_id]

        try:
            # 1. 保存履约记录到信用分模块数据库
            for record in records:
                store.save_performance_record(record)

            # 2. 计算信用分
            score = calculator.calculate(
                agent_id=agent_id,
                wallet=agent_info['wallet'],
                records=records,
                credit_data=credit_data,
                agent_info=agent_info,
            )

            # 3. 保存信用分
            store.save_score(score)

            success_count += 1

            # 进度显示
            profile = agent_id.split('_')[1] if '_' in agent_id else 'unknown'
            print(f"   [{i+1:2d}/{len(dataset['agents'])}] {agent_id:25s} | {profile:10s} | 分数: {score.total_score:5.1f} | 等级: {score.grade}")

        except Exception as e:
            error_count += 1
            print(f"   ❌ {agent_id}: {e}")

    # 结果统计
    print("\n" + "=" * 50)
    print("✅ 数据生成完成!")
    print("=" * 50)
    print(f"   成功: {success_count} 个 Agent")
    print(f"   失败: {error_count} 个 Agent")
    print(f"   总履约记录: {total_records} 条")

    # 验证：读取排行榜
    print("\n📋 信用分排行榜 (Top 10):")
    print("-" * 60)
    leaderboard = store.get_leaderboard(limit=10)
    for entry in leaderboard:
        print(f"   {entry['rank']:2d}. {entry['agent_id']:25s} | {entry['grade']:4s} | {entry['total_score']:5.1f}")

    # 统计信息
    stats = store.get_score_statistics()
    print("\n📊 信用分统计:")
    print(f"   总 Agent 数: {stats['total_agents']}")
    print(f"   平均分: {stats['avg_score']:.1f}")
    print(f"   中位数: {stats['median_score']:.1f}")
    print(f"   等级分布: {stats['grade_counts']}")

    print("\n🎉 完成! 你现在可以:")
    print("   1. 启动 API: python src/api_server.py")
    print("   2. 启动信用分 API: python src/credit/api.py")
    print("   3. 查询信用分: curl localhost:3459/api/v1/credit/<agent_id>")
    print("   4. 查看排行榜: curl localhost:3459/api/v1/credit/leaderboard")


if __name__ == "__main__":
    main()
