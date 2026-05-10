#!/bin/bash
# 验证闭环测试脚本

set -e

echo "=================================="
echo "CryptoMinds 验证闭环测试"
echo "=================================="
echo ""

# 进入项目目录
cd "$(dirname "$0")/.."

# 1. 测试验证闭环
echo "1. 测试验证闭环..."
python3 tools/test_verification.py

# 2. 启动API服务（后台）
echo ""
echo "2. 启动API服务..."
python3 src/api_server.py &
API_PID=$!
sleep 3

# 3. 测试API端点
echo ""
echo "3. 测试API端点..."

# 健康检查
echo "   - 健康检查..."
curl -s http://localhost:3458/health | python3 -m json.tool

# 查询信用分
echo ""
echo "   - 查询信用分..."
curl -s http://localhost:3458/api/v1/credit/test_agent_001 | python3 -m json.tool | head -20

# 获取履约记录
echo ""
echo "   - 获取履约记录..."
curl -s http://localhost:3458/api/v1/credit/test_agent_001/records | python3 -m json.tool | head -20

# 获取验证数据
echo ""
echo "   - 获取验证数据..."
curl -s http://localhost:3458/api/v1/credit/test_agent_001/verify | python3 -m json.tool | head -30

# 4. 测试命令行验证工具
echo ""
echo "4. 测试命令行验证工具..."
python3 tools/verify_credit.py test_agent_001

# 5. 清理
echo ""
echo "5. 清理..."
kill $API_PID 2>/dev/null || true
rm -f test_cryptominds.db test_cryptominds.db-shm test_cryptominds.db-wal

echo ""
echo "=================================="
echo "✅ 所有测试通过！"
echo "=================================="
