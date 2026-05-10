#!/usr/bin/env python3
"""
信用分验证命令行工具

使用方法:
    python verify_credit.py agent_001
    python verify_credit.py agent_001 --api http://localhost:3458
    python verify_credit.py agent_001 --api-key YOUR_KEY
"""

import sys
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="验证CryptoMinds信用分",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("agent_id", help="Agent ID")
    parser.add_argument(
        "--api",
        default="http://localhost:3458",
        help="API基础URL (默认: http://localhost:3458)",
    )
    parser.add_argument("--api-key", help="API密钥（可选）")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")

    args = parser.parse_args()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(repo_root / "sdk" / "python"))
        sys.path.insert(0, str(repo_root / "src"))
        from cryptominds import verify_credit_score

        # 验证
        result = verify_credit_score(
            agent_id=args.agent_id,
            api_url=args.api,
            api_key=args.api_key,
        )

        if args.json:
            print(json.dumps(result, indent=2))
            return 0 if result.get("valid") else 1

        # 人类可读输出
        print("\n" + "=" * 60)
        print(f"信用分验证报告 - {args.agent_id}")
        print("=" * 60)

        if result.get("valid"):
            print("\n✅ 验证成功\n")
            print(f"信用分:     {result['claimed_score']}")
            print(f"等级:       {result['claimed_grade']}")
            print(f"哈希:       {result['claimed_hash']}")
            print(f"\n分数匹配:   {'✓' if result.get('score_match') else '✗'}")
            print(f"等级匹配:   {'✓' if result.get('grade_match') else '✗'}")
            print(f"哈希匹配:   {'✓' if result.get('hash_match') else '✗'}")
        else:
            print("\n❌ 验证失败\n")
            if "error" in result:
                print(f"错误: {result['error']}")
            else:
                print(f"声称的分数: {result.get('claimed_score', 'N/A')}")
                print(f"计算的分数: {result.get('calculated_score', 'N/A')}")
                print(f"声称的等级: {result.get('claimed_grade', 'N/A')}")
                print(f"计算的等级: {result.get('calculated_grade', 'N/A')}")
                print(f"声称的哈希: {result.get('claimed_hash', 'N/A')}")
                print(f"计算的哈希: {result.get('calculated_hash', 'N/A')}")
                print(f"\n分数匹配:   {'✓' if result.get('score_match') else '✗'}")
                print(f"等级匹配:   {'✓' if result.get('grade_match') else '✗'}")
                print(f"哈希匹配:   {'✓' if result.get('hash_match') else '✗'}")

        print("\n" + "=" * 60 + "\n")

        return 0 if result.get("valid") else 1

    except Exception as e:
        print(f"\n❌ 验证失败: {str(e)}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
