#!/bin/bash
# 从本地同步代码到 VPS 并重启服务
# 用法: bash scripts/sync_vps.sh

VPS_HOST="root@cryptominds.cc"
VPS_DIR="/opt/cryptominds"
SSH_KEY="$HOME/.ssh/vps_cryptominds"

echo "=== 同步修改的文件到 VPS ==="

# 前端模块化文件
scp -i "$SSH_KEY" \
  web/views/index.ejs \
  "$VPS_HOST:$VPS_DIR/web/views/"

scp -i "$SSH_KEY" \
  web/public/js/*.js \
  "$VPS_HOST:$VPS_DIR/web/public/js/"

# 后端模块化文件
scp -i "$SSH_KEY" \
  api_server.py \
  "$VPS_HOST:$VPS_DIR/"

scp -i "$SSH_KEY" -r \
  api/ \
  "$VPS_HOST:$VPS_DIR/"

echo "=== 同步完成 ==="
echo "=== 重启服务 ==="

ssh -i "$SSH_KEY" "$VPS_HOST" << 'EOF'
cd /opt/cryptominds

# 创建目录（如果不存在）
mkdir -p web/public/js api/blueprints

# 重启 Python API
supervisorctl restart cryptominds-api
echo "等待 3 秒..."
sleep 3
supervisorctl status

# web 服务不需要重启（静态文件 + EJS 热加载）
echo "Web 服务无需重启（静态文件即时生效）"
EOF

echo "=== 部署完成 ==="
echo "访问 https://cryptominds.cc 检查效果"
