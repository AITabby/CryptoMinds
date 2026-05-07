# 部署指南

## 环境要求

- Python 3.10+
- SQLite 3
- （可选）Node.js 18+（Express 网关）

## 快速启动

### 1. 克隆项目

```bash
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置必要的环境变量：

| 变量 | 必填 | 说明 |
|------|------|------|
| `CRYPTOMINDS_ENV` | 否 | 环境：dev/staging/prod |
| `BSC_RPC` | 是 | BSC RPC 端点 |
| `BSC_CHAIN_ID` | 是 | 链 ID（测试网=97，主网=56） |
| `ESCROW_CONTRACT_ADDRESS` | 是 | 合约地址 |
| `ADMIN_SECRET` | 是 | 管理员密钥 |
| `CRYPTOMINDS_INTERNAL_TOKEN` | 是 | API 内部认证 |

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

```bash
python src/api_server.py
```

服务将在 `http://localhost:3458` 启动。

## 生产部署

### Docker

```bash
# 构建镜像
docker build -t cryptominds-api .

# 运行容器
docker run -d \
  -p 3458:3458 \
  -e CRYPTOMINDS_ENV=prod \
  -e BSC_RPC=https://bsc-dataseed1.binance.org \
  -e BSC_CHAIN_ID=56 \
  -v $(pwd)/data:/app/data \
  cryptominds-api
```

### Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:3458 src.api_server:app
```

## 智能合约部署

### BSC 测试网

```bash
# 使用 Hardhat 或 Remix 部署 contracts/ServiceEscrow.sol
# 记录合约地址到 .env
ESCROW_CONTRACT_ADDRESS=0x...
```

### 合约验证

```bash
# BSCScan 验证
npx hardhat verify --network bsc_testnet <CONTRACT_ADDRESS>
```

## 数据库

项目使用 SQLite，数据库文件位于 `cryptominds.db`。

### 备份

```bash
# 创建备份
cp cryptominds.db cryptominds.db.backup

# 或使用 SQLite 导出
sqlite3 cryptominds.db ".backup 'cryptominds.db.backup'"
```

## 监控

### 健康检查

```bash
curl http://localhost:3458/health
# {"service":"cryptominds-api","status":"ok"}
```

### Prometheus 指标

访问 `http://localhost:3458/metrics` 获取 Prometheus 指标。

## 安全检查清单

- [ ] `.env` 文件未被提交到 Git
- [ ] `ADMIN_SECRET` 使用强随机值（生产环境必须轮换）
- [ ] `CRYPTOMINDS_INTERNAL_TOKEN` 使用强随机值（生产环境必须轮换）
- [ ] 生产环境设置 `DEMO_MODE=false`
- [ ] 生产环境设置 `CRYPTOMINDS_DEBUG=false`
- [ ] 配置 HTTPS（Nginx 反向代理）
- [ ] 配置 CORS 白名单
- [ ] 启用 Rate Limiting

### 生成安全密钥

```bash
# 生成 ADMIN_SECRET
openssl rand -base64 48

# 生成 INTERNAL_TOKEN
openssl rand -base64 48
```

⚠️ **重要**: 生产环境必须使用新生成的密钥，不要使用开发环境的密钥！

## 常见问题

### Q: 启动报错 "address already in use"

```bash
# 查找占用端口的进程
lsof -i :3458

# 终止进程
kill -9 <PID>
```

### Q: 数据库锁定错误

确保只有一个进程访问数据库，或考虑迁移到 PostgreSQL。

### Q: 合约交互失败

检查：
1. `BSC_RPC` 是否正确
2. `BSC_CHAIN_ID` 是否匹配合约所在链
3. 合约地址是否正确
