#!/bin/bash
#
# CryptoMinds 服务启动脚本
#
# 同时启动：
# - Node.js API (3457) - 主入口
# - Python API (3458) - 协议层微服务
#

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$PROJECT_ROOT/web"

echo "=== CryptoMinds 服务启动 ==="
echo ""

# 检查环境
if [ ! -d "$WEB_DIR" ]; then
    echo "错误: web 目录不存在"
    exit 1
fi

# 启动 Python API (后台)
echo "[1] 启动 Python API (3458)..."
cd "$PROJECT_ROOT"
python3 api_server.py &
PYTHON_PID=$!
echo "    Python PID: $PYTHON_PID"

# 等待 Python 服务启动
sleep 2

# 检查 Python 服务是否运行
if ! kill -0 $PYTHON_PID 2>/dev/null; then
    echo "错误: Python API 启动失败"
    exit 1
fi

# 启动 Node.js API (前台)
echo "[2] 启动 Node.js API (3457)..."
cd "$WEB_DIR"
echo ""
echo "=== 服务已启动 ==="
echo "Node.js API: http://localhost:3457"
echo "Python API:  http://localhost:3458"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 捕获退出信号，清理进程
trap "echo ''; echo '停止服务...'; kill $PYTHON_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# 启动 Node.js (前台)
node server_modular.js

# 如果 Node.js 退出，清理 Python
kill $PYTHON_PID 2>/dev/null