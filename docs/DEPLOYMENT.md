# CryptoMinds 部署指南

## 环境要求

- Node.js >= 18
- Python >= 3.9
- Docker + Docker Compose（staging/prod 推荐）
- PostgreSQL（Compose 内置）
- SQLite3（本地 Demo）
- MetaMask 或其他 Web3 钱包

## 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds
```

### 2. 安装依赖
```bash
# Node.js 依赖
cd web
npm install

# Python 依赖（可选，协议层）
cd ..
pip install -r requirements.txt 2>/dev/null || pip3 install web3 requests
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 填入真实值
```

### 4. 启动服务
```bash
# 方式一：同时启动 Node.js + Python
cd web
./start_services.sh

# 方式二：单独启动
npm start                    # Node.js API (3457)
python3 api_server.py        # Python API (3458)

# Demo 模式
npm run demo
```

访问 http://localhost:3457

---

## 服务架构

```
┌─────────────────────────────────────────────┐
│                  客户端                      │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│         Node.js API (端口 3457)             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │ market  │ │  order  │ │  agent  │       │
│  │ routes  │ │ routes  │ │ routes  │       │
│  └─────────┘ └─────────┘ └─────────┘       │
│                    │                         │
│         /api/v1/protocol/* 代理              │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│         Python API (端口 3458)              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │settle-  │ │verify-  │ │ agent   │       │
│  │ment     │ │gates    │ │registry │       │
│  └─────────┘ └─────────┘ └─────────┘       │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│       PostgreSQL (staging/prod) / SQLite     │
└─────────────────────────────────────────────┘
```

---

## 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `CRYPTOMINDS_ENV` | 是 | `dev` / `staging` / `prod` |
| `CRYPTOMINDS_INTERNAL_TOKEN` | staging/prod 是 | 内部服务认证 token，至少 32 字节随机值 |
| `ADMIN_SECRET` | staging/prod 是 | 管理员 API 密钥，至少 32 字节随机值 |
| `POSTGRES_PASSWORD` | staging/prod 是 | Compose Postgres 密码 |
| `BSC_RPC` | 是 | BSC RPC 节点地址；测试网建议 `https://bsc-testnet-dataseed.bnbchain.org` |
| `BSC_CHAIN_ID` | 是 | BSC Mainnet=56，BSC Testnet=97；测试网部署必须设为 `97` |
| `ESCROW_CONTRACT_ADDRESS` | staging/prod 是 | ServiceEscrow 合约地址 |
| `DEPOSIT_POOL_ADDRESS` | 否 | 押金池合约地址 |
| `DEMO_MODE` | 否 | 设为 `true` 开启 Demo 模式 |
| `ADMIN_WALLETS` | 否 | 管理员钱包地址（逗号分隔） |
| `MINIMAX_API_KEY` | 否 | MiniMax API Key（买家平台大脑模式） |
| `VAPID_PUBLIC_KEY` | 否 | Web Push 公钥 |
| `VAPID_PRIVATE_KEY` | 否 | Web Push 私钥 |

环境文件优先级：真实 shell/container 环境变量 > `environments/.env.{env}` > 根目录 `.env`。测试网不要把根目录 `.env` 里的主网 RPC 留成默认值。

---

## BSC Testnet 合约部署

### 1. 编译合约
```bash
make compile-contracts
```

### 2. 准备部署钱包

部署脚本读取 `wallets.json` 里的 `four_meme` 钱包。该钱包必须是测试网专用钱包，并准备少量 `tBNB`。

```bash
chmod 600 wallets.json
```

可以从 BNB 官方 Faucet 或 QuickNode/Chainstack Faucet 领取 BSC Testnet `tBNB`。

### 3. 部署到 BSC Testnet
```bash
BSC_RPC=https://bsc-testnet-dataseed.bnbchain.org \
BSC_CHAIN_ID=97 \
node scripts/deploy_service_escrow.js
```

部署脚本会拒绝缺失 `BSC_RPC`、拒绝 RPC chainId 与 `BSC_CHAIN_ID` 不一致、并默认拒绝主网部署。部署成功后会生成 `escrow_deployment.json`，其中同时包含 `contractAddress` 和 `address`。

### 4. 更新环境变量
```bash
ESCROW_CONTRACT_ADDRESS=0x...
```

---

## Staging 部署

推荐一台小 VPS 直接跑 Docker Compose。只公开 Nginx 的 `80/443`，不要公开 Python API、Postgres 或 Agent 端口。

### 1. 配置 `environments/.env.staging`

```bash
cp environments/.env.staging.template environments/.env.staging

CRYPTOMINDS_ENV=staging
DEMO_MODE=false
CRYPTOMINDS_DEBUG=false
CRYPTOMINDS_INTERNAL_TOKEN=<openssl rand -hex 32>
ADMIN_SECRET=<openssl rand -hex 32>
POSTGRES_PASSWORD=<openssl rand -hex 32>
BSC_RPC=https://bsc-testnet-dataseed.bnbchain.org
BSC_CHAIN_ID=97
ESCROW_CONTRACT_ADDRESS=0x...
ALLOWED_ORIGINS=https://testnet.example.com
```

### 2. 配置 HTTPS

```bash
bash nginx/ssl-setup.sh testnet.example.com you@example.com
```

### 3. 启动

```bash
bash scripts/deploy.sh staging
curl https://testnet.example.com/healthz
```

### 4. 查看日志

```bash
docker-compose logs -f web-api
docker-compose logs -f python-api
```

---

## 测试

### 运行所有测试
```bash
./tests/run_all_tests.sh
```

### 单独测试
```bash
# Python 测试
python3 tests/test_verification.py -v
python3 tests/test_settlement.py -v

# Node.js 测试
cd web && npm test
```

### API 集成测试
```bash
node web/test_api.js
```

---

## 数据库

### 数据库位置
```
staging/prod: Postgres volume `pgdata`
local demo: web/cryptominds.db
```

### 数据库表结构
- `sellers` - 卖家信息
- `orders` - 订单记录
- `purchases` - 购买记录
- `tx_logs` - 交易日志
- `notifications` - 通知
- `push_subs` - Web Push 订阅
- `agents` - Agent 注册信息

### 数据迁移
如果从旧版本 JSON 数据迁移：
```bash
cd web
node migrate_to_sqlite.js
```

---

## 常见问题

### Q: 合约未部署错误
A: 检查 `escrow_deployment.json` 是否存在，或设置 `ESCROW_CONTRACT_ADDRESS` 环境变量。新部署文件里的 `contractAddress` / `address` 都可被运行时读取。

### Q: MetaMask 连接失败
A: 确保浏览器已安装 MetaMask，且网络切换到 BSC Testnet：chainId `97`，symbol `tBNB`。

### Q: 测试网交易签名失败
A: 检查 `BSC_RPC` 指向测试网，且 `BSC_CHAIN_ID=97`。后端会校验 RPC 实际 chainId，防止测试网 RPC 用主网 chainId 签名。

### Q: Demo 模式下支付失败
A: Demo 模式会跳过支付验证，检查后端日志确认。

---

## 联系方式

- GitHub: https://github.com/AITabby/CryptoMinds
- 黑客松: Four.meme AI Sprint 2026
