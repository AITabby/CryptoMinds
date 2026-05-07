#!/usr/bin/env python3
"""
同步信用分数据到主数据库

将 credit_score/credit_score.db 的数据同步到 cryptominds.db
"""

import sqlite3
import os
import sys

# 切换到项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

SOURCE_DB = "credit_score/credit_score.db"
TARGET_DB = "cryptominds.db"


def sync_table(source_conn, target_conn, table_name, columns):
    """同步单个表"""
    cursor = source_conn.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    col_names = [d[0] for d in cursor.description]

    if not rows:
        print(f"   {table_name}: 无数据")
        return 0

    placeholders = ", ".join(["?" for _ in col_names])
    col_str = ", ".join(col_names)

    # 使用 INSERT OR REPLACE 避免主键冲突
    sql = f"INSERT OR REPLACE INTO {table_name} ({col_str}) VALUES ({placeholders})"

    count = 0
    for row in rows:
        try:
            target_conn.execute(sql, row)
            count += 1
        except Exception as e:
            print(f"   错误: {e}")
            continue

    return count


def main():
    print("=" * 50)
    print("同步信用分数据到主数据库")
    print("=" * 50)

    if not os.path.exists(SOURCE_DB):
        print(f"❌ 源数据库不存在: {SOURCE_DB}")
        return

    if not os.path.exists(TARGET_DB):
        print(f"❌ 目标数据库不存在: {TARGET_DB}")
        return

    source = sqlite3.connect(SOURCE_DB)
    source.row_factory = sqlite3.Row

    target = sqlite3.connect(TARGET_DB)
    target.row_factory = sqlite3.Row

    print(f"\n源数据库: {SOURCE_DB}")
    print(f"目标数据库: {TARGET_DB}\n")

    # 同步表
    tables = [
        ("sacred_scores", None),
        ("dimension_details", None),
        ("performance_records", None),
        ("severe_violations", None),
    ]

    total_synced = 0
    for table, _ in tables:
        count = sync_table(source, target, table, None)
        total_synced += count
        print(f"   ✓ {table}: 同步 {count} 条记录")

    target.commit()
    source.close()
    target.close()

    print(f"\n✅ 同步完成! 共同步 {total_synced} 条记录")

    # 验证
    print("\n📊 验证结果:")
    target = sqlite3.connect(TARGET_DB)
    for table, _ in tables:
        count = target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"   {table}: {count} 条")

    target.close()


if __name__ == "__main__":
    main()
