# CryptoMinds 部署指南

## 环境要求

- Node.js >= 18
- Python >= 3.9
- SQLite3
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
│         /api/protocol/* 代理                 │
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
│              SQLite (cryptominds.db)        │
└─────────────────────────────────────────────┘
```

---

## 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `BSC_RPC` | 是 | BSC RPC 节点地址 |
| `ESCROW_CONTRACT_ADDRESS` | 是 | Escrow 合约地址 |
| `DEPOSIT_POOL_ADDRESS` | 否 | 押金池合约地址 |
| `DEMO_MODE` | 否 | 设为 `true` 开启 Demo 模式 |
| `ADMIN_SECRET` | 否 | 管理员 API 密钥 |
| `ADMIN_WALLETS` | 否 | 管理员钱包地址（逗号分隔） |
| `MINIMAX_API_KEY` | 否 | MiniMax API Key（买家平台大脑模式） |
| `VAPID_PUBLIC_KEY` | 否 | Web Push 公钥 |
| `VAPID_PRIVATE_KEY` | 否 | Web Push 私钥 |

---

## 合约部署

### 1. 编译合约
```bash
cd contracts
solcjs --abi --bin ServiceEscrow.sol
```

### 2. 部署到 BSC
```bash
cd ..
node scripts/deploy_service_escrow.js
```

部署成功后会生成 `escrow_deployment.json`。

### 3. 更新环境变量
```bash
echo "ESCROW_CONTRACT_ADDRESS=0x..." >> .env
```

---

## 生产部署

### Docker
```bash
docker build -t cryptominds .
docker run -p 3457:3457 --env-file .env cryptominds
```

### PM2
```bash
pm2 start web/server.js --name cryptominds
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
node tests/test_database.js
```

### API 集成测试
```bash
node web/test_api.js
```

---

## 数据库

### 数据库位置
```
web/cryptominds.db
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
A: 检查 `escrow_deployment.json` 是否存在，或设置 `ESCROW_CONTRACT_ADDRESS` 环境变量。

### Q: MetaMask 连接失败
A: 确保浏览器已安装 MetaMask，且网络切换到 BSC。

### Q: Demo 模式下支付失败
A: Demo 模式会跳过支付验证，检查后端日志确认。

---

## 联系方式

- GitHub: https://github.com/AITabby/CryptoMinds
- 黑客松: Four.meme AI Sprint 2026
