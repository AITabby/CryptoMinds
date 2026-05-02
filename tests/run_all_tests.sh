#!/bin/bash
#
# CryptoMinds 测试运行脚本
#

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== CryptoMinds 测试套件 ==="
echo ""

# Python 测试
echo "[1] Python 测试..."
cd "$PROJECT_ROOT"
python3 tests/test_verification.py -v
echo ""

echo "[2] 结算通道测试..."
python3 tests/test_settlement.py -v
echo ""

echo "[3] 协议回归测试..."
python3 tests/test_protocol_regressions.py -v
echo ""

# Node.js 测试
echo "[4] Node.js 单元测试..."
cd "$PROJECT_ROOT"
node --test tests/*.test.js
echo ""

echo "=== 所有测试完成 ==="