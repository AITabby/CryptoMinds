#!/bin/bash
# CryptoMinds 一键启动脚本
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🚀 CryptoMinds PoC 启动中..."

# 1. 检查 .env
if [ ! -f .env ]; then
    echo "⚠️  .env 不存在，使用默认配置"
fi

# 2. 检查 wallets.json
if [ ! -f wallets.json ]; then
    echo "❌ wallets.json 不存在，请先配置钱包"
    exit 1
fi

# 3. 检查端口占用
check_port() {
    if lsof -i :$1 >/dev/null 2>&1; then
        echo "⚠️  端口 $1 已占用，跳过"
        return 1
    fi
    return 0
}

# 4. 启动 Web Dashboard
if check_port 3456; then
    echo "📦 启动 Web Dashboard (port 3456)..."
    cd "$DIR/web"
    if [ ! -d node_modules ]; then
        npm install --silent 2>/dev/null || true
    fi
    node server.js > /dev/null 2>&1 &
    WEB_PID=$!
    echo "  ✅ Web Dashboard PID: $WEB_PID"
    cd "$DIR"
fi

# 5. 等待服务就绪
sleep 2

# 6. 健康检查
echo ""
echo "🩺 健康检查..."
if curl -s http://localhost:3456/api/market >/dev/null 2>&1; then
    echo "  ✅ Web Dashboard: http://localhost:3456"
else
    echo "  ⚠️  Web Dashboard 未响应，请检查日志"
fi

echo ""
echo "✅ Demo ready!"
echo "  📊 Dashboard: http://localhost:3456"
echo "  🔧 调度器:    python3 orchestrator.py '帮我买 meme 币'"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待后台进程
wait
