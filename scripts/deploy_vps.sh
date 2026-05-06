#!/bin/bash
# CryptoMinds VPS 一键部署脚本
# 在 VPS 上运行: bash deploy_vps.sh

set -e

echo "========================================"
echo " CryptoMinds VPS 部署"
echo "========================================"

# 1. 安装依赖
echo "[1/6] 安装系统依赖..."
apt update
apt install -y python3 python3-pip nodejs npm nginx git supervisor

echo "[2/6] 安装 Python 依赖..."
pip3 install flask web3 gunicorn python-dotenv

# 2. 克隆项目（如果没有）
PROJECT_DIR="/opt/cryptominds"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "[3/6] 克隆项目..."
    # 如果是从 GitHub 克隆:
    # git clone https://github.com/你的用户名/cryptominds.git $PROJECT_DIR

    # 如果是手动上传的，这里跳过
    echo "请确保项目代码已放在 $PROJECT_DIR"
    echo "可以用 scp 从本地上传:"
    echo "  scp -r /Users/aitabby/projects/cryptominds root@148.135.6.154:$PROJECT_DIR"
    mkdir -p $PROJECT_DIR
fi

cd $PROJECT_DIR

# 3. 配置环境变量
echo "[4/6] 配置环境..."
if [ ! -f .env ]; then
    cp .env.example .env
fi

# 设置测试网合约地址
ESCROW_CONTRACT_ADDRESS="0xe9C878845F7299C00Ff6465B02f43De2a1b49b62"

# 更新 .env 关键配置
sed -i "s/^BSC_RPC=.*/BSC_RPC=https:\/\/data-seed-prebsc-1-s1.bnbchain.org:8545/" .env
sed -i "s/^BSC_CHAIN_ID=.*/BSC_CHAIN_ID=97/" .env
sed -i "s/^ESCROW_CONTRACT_ADDRESS=.*/ESCROW_CONTRACT_ADDRESS=$ESCROW_CONTRACT_ADDRESS/" .env
sed -i "s/^DEMO_MODE=.*/DEMO_MODE=false/" .env
sed -i "s/^CRYPTOMINDS_DEBUG=.*/CRYPTOMINDS_DEBUG=false/" .env

echo "  合约地址: $ESCROW_CONTRACT_ADDRESS"
echo "  网络: BSC Testnet"

# 4. 初始化信用分数据
echo "[5/6] 生成信用分模拟数据..."
if [ ! -f credit_score/credit_score.db ]; then
    python3 -c "
from credit_score.generator import CreditScoreDataGenerator
gen = CreditScoreDataGenerator(db_path='credit_score/credit_score.db', credit_db_path='credit_score/credit_score.db', seed=42)
stats = gen.generate()
print('Done: {} agents, {} records'.format(stats['total_agents'], stats['total_records']))
"
else
    echo "  信用分数据已存在，跳过"
fi

# 5. 配置 Nginx
echo "[6/6] 配置 Nginx..."
cat > /etc/nginx/sites-available/cryptominds << 'NGINX'
server {
    listen 80;
    server_name 148.135.6.154;

    # 主 API
    location /api/v1/ {
        proxy_pass http://127.0.0.1:3458;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 信用分 API
    location /api/v1/credit-score/ {
        proxy_pass http://127.0.0.1:3459/api/v1/credit-score/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 信用分 Dashboard
    location /credit/ {
        proxy_pass http://127.0.0.1:3459/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 主 Dashboard
    location / {
        proxy_pass http://127.0.0.1:3457;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

ln -sf /etc/nginx/sites-available/cryptominds /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# 6. 配置 Supervisor（进程守护）
cat > /etc/supervisor/conf.d/cryptominds.conf << 'SUPV'
[program:cryptominds-api]
command=gunicorn --bind 127.0.0.1:3458 --workers 2 --threads 4 api_server:app
directory=/opt/cryptominds
environment=FLASK_APP=api_server.py
autostart=true
autorestart=true
stderr_logfile=/var/log/cryptominds-api.err.log
stdout_logfile=/var/log/cryptominds-api.out.log

[program:cryptominds-credit]
command=python3 -m credit_score.api
directory=/opt/cryptominds
environment=CREDIT_SCORE_DB_PATH="/opt/cryptominds/credit_score/credit_score.db",CRYPTOMINDS_DB_PATH="/opt/cryptominds/cryptominds.db"
autostart=true
autorestart=true
stderr_logfile=/var/log/cryptominds-credit.err.log
stdout_logfile=/var/log/cryptominds-credit.out.log

[program:cryptominds-web]
command=node server_modular.js
directory=/opt/cryptominds/web
autostart=true
autorestart=true
stderr_logfile=/var/log/cryptominds-web.err.log
stdout_logfile=/var/log/cryptominds-web.out.log
SUPV

supervisorctl update

echo ""
echo "========================================"
echo " 部署完成！"
echo "========================================"
echo ""
echo "访问地址:"
echo "  主 Dashboard:  http://148.135.6.154"
echo "  信用分面板:    http://148.135.6.154/credit/"
echo "  主 API:        http://148.135.6.154/api/v1/"
echo "  信用分 API:    http://148.135.6.154/api/v1/credit-score/"
echo ""
echo "合约:  $ESCROW_CONTRACT_ADDRESS"
echo "BSCscan: https://testnet.bscscan.com/address/$ESCROW_CONTRACT_ADDRESS"
echo ""
echo "管理命令:"
echo "  supervisorctl status          # 查看服务状态"
echo "  supervisorctl restart all     # 重启所有服务"
echo "  supervisorctl stop all        # 停止所有服务"
echo "  tail -f /var/log/cryptominds-*.log  # 查看日志"