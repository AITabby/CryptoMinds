# CryptoMinds 部署指南

## 快速部署（5分钟）

### 1. 服务器要求

**最低配置：**
- CPU: 1核
- RAM: 1GB
- 存储: 10GB
- 系统: Ubuntu 20.04+

**推荐配置：**
- CPU: 2核
- RAM: 2GB
- 存储: 20GB
- 带宽: 10Mbps

### 2. 域名和SSL

```bash
# 购买域名（推荐）
api.cryptominds.io

# 配置DNS A记录
A    api    <服务器IP>
A    www    <服务器IP>
```

### 3. 一键部署脚本

```bash
# 下载部署脚本
curl -O https://raw.githubusercontent.com/AITabby/CryptoMinds/main/deploy/deploy.sh
chmod +x deploy.sh

# 运行部署
./deploy.sh
```

## 详细部署步骤

### Step 1: 准备服务器

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装依赖
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git

# 创建用户
sudo useradd -m -s /bin/bash cryptominds
sudo su - cryptominds
```

### Step 2: 克隆代码

```bash
# 克隆仓库
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### Step 3: 配置环境

```bash
# 创建配置文件
cat > .env << 'ENVEOF'
# API配置
CRYPTOMINDS_API_PORT=3458
CRYPTOMINDS_REQUIRE_AUTH=true
CRYPTOMINDS_API_KEY=replace-with-a-long-random-key

# 数据库配置
CRYPTOMINDS_DB_PATH=/home/cryptominds/data/cryptominds.db

# 日志配置
LOG_LEVEL=INFO
LOG_PATH=/home/cryptominds/logs

# 监控配置
ENABLE_METRICS=true
METRICS_PORT=9090
ENVEOF

# 创建目录
mkdir -p /home/cryptominds/data
mkdir -p /home/cryptominds/logs
```

### Step 4: 配置Systemd服务

```bash
# 创建服务文件
sudo tee /etc/systemd/system/cryptominds.service > /dev/null << 'SVCEOF'
[Unit]
Description=CryptoMinds API Service
After=network.target

[Service]
Type=simple
User=cryptominds
WorkingDirectory=/home/cryptominds/CryptoMinds
Environment="PATH=/home/cryptominds/CryptoMinds/venv/bin"
EnvironmentFile=/home/cryptominds/CryptoMinds/.env
ExecStart=/home/cryptominds/CryptoMinds/venv/bin/python src/api_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable cryptominds
sudo systemctl start cryptominds

# 检查状态
sudo systemctl status cryptominds
```

### Step 5: 配置Nginx反向代理

```bash
# 创建Nginx配置
sudo tee /etc/nginx/sites-available/cryptominds > /dev/null << 'NGXEOF'
server {
    listen 80;
    server_name api.cryptominds.io;

    location / {
        proxy_pass http://127.0.0.1:3458;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:3458/health;
        access_log off;
    }
}
NGXEOF

# 启用配置
sudo ln -s /etc/nginx/sites-available/cryptominds /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 6: 配置SSL证书

```bash
# 自动获取Let's Encrypt证书
sudo certbot --nginx -d api.cryptominds.io

# 自动续期
sudo certbot renew --dry-run
```

### Step 7: 配置防火墙

```bash
# 允许HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### Step 8: 验证部署

```bash
# 测试API
curl https://api.cryptominds.io/health

# 测试信用分查询
curl https://api.cryptominds.io/api/v1/credit/test_agent_001
```

## 监控和日志

### 日志查看

```bash
# 查看服务日志
sudo journalctl -u cryptominds -f

# 查看应用日志
tail -f /home/cryptominds/logs/api.log

# 查看Nginx日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 数据库备份

```bash
# 创建备份脚本
cat > /home/cryptominds/backup.sh << 'BKEOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/home/cryptominds/backups
mkdir -p $BACKUP_DIR

# 备份数据库
sqlite3 /home/cryptominds/data/cryptominds.db ".backup '$BACKUP_DIR/cryptominds_$DATE.db'"

# 删除30天前的备份
find $BACKUP_DIR -name "cryptominds_*.db" -mtime +30 -delete

echo "Backup completed: cryptominds_$DATE.db"
BKEOF

chmod +x /home/cryptominds/backup.sh

# 添加到crontab（每天凌晨2点备份）
(crontab -l 2>/dev/null; echo "0 2 * * * /home/cryptominds/backup.sh") | crontab -
```

## 成本估算

### 云服务器（月费）

| 提供商 | 配置 | 价格 |
|--------|------|------|
| DigitalOcean | 1GB RAM, 1 CPU | $6/月 |
| Linode | 2GB RAM, 1 CPU | $12/月 |
| AWS Lightsail | 1GB RAM, 1 CPU | $5/月 |
| Vultr | 1GB RAM, 1 CPU | $6/月 |

### 域名（年费）

- .io域名：$30-50/年
- .com域名：$10-15/年

### SSL证书

- Let's Encrypt：免费
- 商业证书：$50-200/年

**总成本：$72-144/年（最低配置）**

## 故障排查

### 服务无法启动

```bash
# 检查日志
sudo journalctl -u cryptominds -n 50

# 检查端口占用
sudo lsof -i :3458

# 检查权限
ls -la /home/cryptominds/data
ls -la /home/cryptominds/logs
```

### 数据库锁定

```bash
# 检查WAL模式
sqlite3 /home/cryptominds/data/cryptominds.db "PRAGMA journal_mode;"

# 应该返回 "wal"
# 如果不是，执行：
sqlite3 /home/cryptominds/data/cryptominds.db "PRAGMA journal_mode=WAL;"
```

## 联系支持

遇到问题？
- Email: aitabbyspace@gmail.com
- GitHub Issues: github.com/AITabby/CryptoMinds/issues
- Twitter: @aitabby
