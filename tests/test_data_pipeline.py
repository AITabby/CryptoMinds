"""
测试数据采集和评分区分度

验证不同信用档案的 Agent 能否被正确区分。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector.mock_data import MockDataGenerator
from src.credit.calculator import SacredCalculator
from src.credit.store import CreditScoreStore


def test_score_differentiation():
    """测试评分区分度"""
    print("=" * 60)
    print("CryptoMinds 信用分区分度测试")
    print("=" * 60)

    # 生成测试数据
    generator = MockDataGenerator(seed=42)
    calculator = SacredCalculator()

    dataset = generator.generate_test_dataset(
        agents_per_profile=3,
        days=90,
    )

    print(f"\n生成了 {len(dataset['agents'])} 个 Agent 的测试数据\n")

    # 按档案分组统计
    results = {
        "high": [],
        "medium": [],
        "low": [],
        "malicious": [],
    }

    for agent_info in dataset["agents"]:
        agent_id = agent_info["agent_id"]
        profile = agent_id.split("_")[1]  # agent_high_1 -> high

        records = dataset["records"][agent_id]
        credit_data = dataset["credit_data"][agent_id]

        # 计算信用分
        score = calculator.calculate(
            agent_id=agent_id,
            wallet=agent_info["wallet"],
            records=records,
            credit_data=credit_data,
            agent_info=agent_info,
        )

        results[profile].append({
            "agent_id": agent_id,
            "total_score": score.total_score,
            "grade": score.grade,
            "dimensions": {k: round(v.weighted_score, 1) for k, v in score.dimensions.items()},
        })

    # 打印结果
    for profile, scores in results.items():
        if not scores:
            continue

        avg_score = sum(s["total_score"] for s in scores) / len(scores)
        grades = [s["grade"] for s in scores]

        print(f"\n{profile.upper()} 信用档案:")
        print("-" * 40)
        print(f"  Agent 数: {len(scores)}")
        print(f"  平均分: {avg_score:.1f}")
        print(f"  等级分布: {', '.join(grades)}")

        for s in scores:
            dims = s["dimensions"]
            print(f"  {s['agent_id']}: {s['total_score']:.0f} ({s['grade']})")
            print(f"    S={dims['S']:.0f} A={dims['A']:.0f} C={dims['C']:.0f} "
                  f"R={dims['R']:.0f} E={dims['E']:.0f}")

    # 验证区分度
    print("\n" + "=" * 60)
    print("区分度验证")
    print("=" * 60)

    high_avg = sum(s["total_score"] for s in results["high"]) / len(results["high"])
    medium_avg = sum(s["total_score"] for s in results["medium"]) / len(results["medium"])
    low_avg = sum(s["total_score"] for s in results["low"]) / len(results["low"])
    malicious_avg = sum(s["total_score"] for s in results["malicious"]) / len(results["malicious"])

    print(f"\n高信用 Agent 平均分: {high_avg:.1f}")
    print(f"中等信用 Agent 平均分: {medium_avg:.1f}")
    print(f"低信用 Agent 平均分: {low_avg:.1f}")
    print(f"恶意 Agent 平均分: {malicious_avg:.1f}")

    # 检查区分度
    print("\n区分度检查:")
    checks = [
        ("高 vs 中等", high_avg > medium_avg + 50),
        ("中等 vs 低", medium_avg > low_avg + 50),
        ("低 vs 恶意", low_avg > malicious_avg + 50),
        ("高 vs 恶意", high_avg > malicious_avg + 200),
    ]

    all_passed = True
    for name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✓ 所有区分度检查通过！")
    else:
        print("\n✗ 部分区分度检查失败，需要调整评分参数。")

    return all_passed


def test_record_statistics():
    """测试记录统计"""
    print("\n" + "=" * 60)
    print("履约记录统计")
    print("=" * 60)

    generator = MockDataGenerator(seed=42)

    for profile in ["high", "medium", "low", "malicious"]:
        agent_id = generator.generate_agent_id(profile)
        records = generator.generate_records(agent_id, profile, days=90)

        success = sum(1 for r in records if r.status.value == "settled")
        timeout = sum(1 for r in records if r.status.value == "timeout")
        failed = sum(1 for r in records if r.status.value == "failed")
        disputed = sum(1 for r in records if r.disputed)

        print(f"\n{profile.upper()} 档案 ({len(records)} 条记录):")
        print(f"  成功: {success} ({success/len(records)*100:.1f}%)")
        print(f"  超时: {timeout} ({timeout/len(records)*100:.1f}%)")
        print(f"  失败: {failed} ({failed/len(records)*100:.1f}%)")
        print(f"  争议: {disputed} ({disputed/len(records)*100:.1f}%)")


if __name__ == "__main__":
    test_record_statistics()
    test_score_differentiation()
