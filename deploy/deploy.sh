#!/bin/bash
# CryptoMinds 一键部署脚本

set -e

echo "=================================="
echo "CryptoMinds 部署脚本"
echo "=================================="
echo ""

# 检查是否为root用户
if [ "$EUID" -eq 0 ]; then 
    echo "❌ 请不要使用root用户运行此脚本"
    exit 1
fi

# 检查系统
if ! command -v apt &> /dev/null; then
    echo "❌ 此脚本仅支持Ubuntu/Debian系统"
    exit 1
fi

# 1. 安装依赖
echo "1. 安装系统依赖..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git sqlite3

# 2. 克隆代码
echo ""
echo "2. 克隆代码..."
if [ -d "CryptoMinds" ]; then
    echo "   目录已存在，跳过克隆"
    cd CryptoMinds
    git pull
else
    git clone https://github.com/AITabby/CryptoMinds.git
    cd CryptoMinds
fi

# 3. 创建虚拟环境
echo ""
echo "3. 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 4. 安装Python依赖
echo ""
echo "4. 安装Python依赖..."
pip install -r requirements.txt

# 5. 创建目录
echo ""
echo "5. 创建数据目录..."
mkdir -p data logs

# 6. 初始化数据库
echo ""
echo "6. 初始化数据库..."
python3 << 'PYEOF'
import sys
sys.path.insert(0, "src")
from store import UnifiedStore

store = UnifiedStore("data/cryptominds.db")
print("✅ 数据库初始化完成")
PYEOF

# 7. 测试API
echo ""
echo "7. 测试API服务..."
python3 src/api_server.py &
API_PID=$!
sleep 3

if curl -s http://localhost:3458/health > /dev/null; then
    echo "✅ API服务正常"
else
    echo "❌ API服务启动失败"
    kill $API_PID 2>/dev/null || true
    exit 1
fi

kill $API_PID 2>/dev/null || true

# 8. 完成
echo ""
echo "=================================="
echo "✅ 部署完成！"
echo "=================================="
echo ""
echo "下一步："
echo "1. 启动服务: python3 src/api_server.py"
echo "2. 测试API: curl http://localhost:3458/health"
echo "3. 查看文档: cat docs/API.md"
echo ""
echo "生产部署请参考: docs/DEPLOYMENT.md"
echo ""
