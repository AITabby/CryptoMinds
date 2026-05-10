#!/usr/bin/env python3
"""
测试验证闭环

生成测试数据，测试信用分计算和验证
"""

import sys
import os
import time

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from credit.calculator import SacredCalculator
from credit.models import PerformanceRecord, TaskStatus
from store import UnifiedStore


def generate_test_records(agent_id: str, count: int = 10) -> list:
    """生成测试履约记录"""
    records = []
    now = int(time.time())

    for i in range(count):
        record = PerformanceRecord(
            record_id=f"test_rec_{i:03d}",
            task_id=f"test_task_{i:03d}",
            task_type="token_delivery",
            buyer_wallet=f"0xbuyer{i:03d}",
            seller_wallet=f"0x{agent_id}",
            seller_agent_id=agent_id,
            chain="bsc",
            amount="0.1",
            status=TaskStatus.SETTLED if i % 10 != 0 else TaskStatus.TIMEOUT,
            success=i % 10 != 0,
            score=0.8 + (i % 3) * 0.1,
            created_at=now - (count - i) * 86400,  # 每天一个
            completed_at=now - (count - i) * 86400 + 3600,
            response_time_ms=1000 + i * 100,
            payment_tx=f"0xtx{i:03d}",
            payment_amount="0.1",
            evidence="test_evidence",
            disputed=False,
            dispute_reason="",
            resolution="",
        )
        records.append(record)

    return records


def test_verification_loop():
    """测试验证闭环"""
    print("\n" + "=" * 60)
    print("测试验证闭环")
    print("=" * 60 + "\n")

    # 1. 初始化
    print("1. 初始化存储和计算器...")
    store = UnifiedStore("test_cryptominds.db")
    calculator = SacredCalculator()

    # 2. 生成测试数据
    print("2. 生成测试数据...")
    agent_id = "test_agent_001"
    records = generate_test_records(agent_id, count=20)

    # 保存履约记录
    for record in records:
        store.save_performance_record(record)
    print(f"   生成了 {len(records)} 条履约记录")

    # 3. 计算信用分
    print("3. 计算信用分...")
    score = calculator.calculate(
        agent_id=agent_id,
        wallet=f"0x{agent_id}",
        records=records,
    )
    print(f"   总分: {score.total_score}")
    print(f"   等级: {score.grade}")
    print(f"   哈希: {score.snapshot_hash}")

    # 保存信用分
    store.save_score(score)

    # 4. 验证信用分
    print("4. 验证信用分...")

    # 重新读取
    saved_score = store.get_latest_score(agent_id)
    saved_records = store.get_performance_records(agent_id=agent_id)

    # 重新计算
    recalculated = calculator.calculate(
        agent_id=agent_id,
        wallet=f"0x{agent_id}",
        records=saved_records,
        now=saved_score.calculated_at,
    )

    # 对比
    score_match = abs(saved_score.total_score - recalculated.total_score) < 0.1
    grade_match = saved_score.grade == recalculated.grade
    hash_match = saved_score.snapshot_hash == recalculated.snapshot_hash

    print(f"   分数匹配: {'✓' if score_match else '✗'}")
    print(f"   等级匹配: {'✓' if grade_match else '✗'}")
    print(f"   哈希匹配: {'✓' if hash_match else '✗'}")

    if score_match and grade_match and hash_match:
        print("\n✅ 验证成功！验证闭环正常工作。")
        return 0
    else:
        print("\n❌ 验证失败！")
        print(f"   保存的分数: {saved_score.total_score}")
        print(f"   重算的分数: {recalculated.total_score}")
        print(f"   保存的哈希: {saved_score.snapshot_hash}")
        print(f"   重算的哈希: {recalculated.snapshot_hash}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = test_verification_loop()
        print("\n" + "=" * 60 + "\n")
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
