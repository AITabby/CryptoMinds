# CryptoMinds

**AI Agent 信任基础设施 — 信用分 + 可信交易协议**

CryptoMinds 是 BNB Chain 上的 AI Agent 信任层。通过 SACRED 五维信用分评估 Agent 可信度，通过链上 Escrow 协议保障 Agent 间交易安全。信用分驱动交易门槛，交易数据反哺信用评估，形成信任飞轮。

[![BSC Testnet](https://img.shields.io/badge/BSC-Testnet-green?logo=binance)](https://testnet.bscscan.com/address/0xe9C878845F7299C00Ff6465B02f43De2a1b49b62)
[![Tests](https://img.shields.io/badge/tests-292%20passed-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## 核心功能

### SACRED 信用分体系

五维度评估 Agent 可信度，标准化 AAA-C 等级：

| 维度 | 评估内容 | 满分 |
|------|---------|------|
| **S**tability | 成功率 + 超时率 + 活跃度 | 200 |
| **A**ctivity | 近期任务量 + 连续活跃 + 时段覆盖 | 200 |
| **C**reditworthiness | 质押量 + 托管金额 + 信用货币接受度 | 200 |
| **R**eliability | 争议赢率 + 验证评分 + 违规惩罚 | 200 |
| **E**cosystem | 交互数 + 信任网络 + 跨链活跃 | 200 |

- 时间衰减加权：近期行为权重更高
- 冷启动保护：新 Agent 基础分 250，3 笔交易退出冷启动
- 查询授权：Agent 签名授权第三方查询，支持链上签名验证
- 快照哈希：防篡改，每次计算结果可验证

### 链上 Escrow 协议

11 态状态机保障交易安全：

```
创建 → 托管 → 交付 → 确认放款
                ↓
             争议 → 仲裁（退款/放款）
                ↓
          超时自动处理
```

- **ServiceEscrow.sol** — BSC 链上合约，BNB 托管
- 信誉加权仲裁：信用分高的 Agent 仲裁权重更大
- Seller slashing：恶意行为自动惩罚
- 三分支验证：自动验证 / 争议仲裁 / 超时处理

### 多链结算

BSC（ERC20 + 原生 BNB）· Solana（SOL）· Polygon（规划中）

---

## 测试网 Demo

合约已部署在 BSC 测试网，3 笔演示交易覆盖完整场景：

[在 BSCscan 上查看合约 →](https://testnet.bscscan.com/address/0xe9C878845F7299C00Ff6465B02f43De2a1b49b62)

```bash
# 快速启动
cp .env.example .env
bash demo.sh

# 或手动启动
python3 api_server.py              # Python API :3458
cd web && node server_modular.js   # Express + Dashboard :3457
python3 -m credit_score.api        # 信用分 API :3459
```

### 部署到 BSC 测试网

```bash
# 1. 领测试 BNB: https://www.bnbchain.org/en/testnet-faucet
# 2. 部署合约
DEPLOY_PRIVATE_KEY=0x... python3 scripts/deploy_testnet.py

# 3. 跑演示交易
DEPLOY_PRIVATE_KEY=0x... python3 scripts/demo_transactions.py

# 4. 启动服务（含 Cloudflare Tunnel 公网暴露）
./scripts/start_demo.sh
```

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                  API Layer                       │
│          Flask + Gunicorn / Express              │
├─────────────┬──────────────┬────────────────────┤
│  Credit Score│   Escrow     │   Credit Currency  │
│  (独立模块)  │   Engine     │   System           │
├─────────────┴──────────────┴────────────────────┤
│           Settlement Layer (Multi-chain)         │
│        BSC (ERC20)  ·  Solana  ·  Polygon       │
├─────────────────────────────────────────────────┤
│  Data: PostgreSQL / SQLite  ·  Security: Fernet  │
│  Monitoring: Prometheus + Sentry  ·  Docker      │
└─────────────────────────────────────────────────┘
```

---

## 项目结构

```
cryptominds/
├── contracts/             # ServiceEscrow.sol + 编译产物
├── credit_score/          # SACRED 信用分（独立模块，可脱离运行）
│   ├── calculator.py      # 五维计算引擎
│   ├── models.py          # TaskStatus + PerformanceRecord + SacredScore
│   ├── api.py             # Flask 蓝图 + 独立运行入口
│   ├── cold_start.py      # 冷启动逻辑
│   ├── store.py           # 独立 SQLite 持久化
│   └── dashboard/         # 信用分面板
├── settlement/            # Escrow 状态机
├── escrow/                # 仲裁 + slashing
├── reputation/            # 履约记录
├── data/                  # SQLite / PostgreSQL 存储
├── auth/                  # Session Key + 链上签名
├── verification/          # 验证门框架
├── agent/                 # Agent 注册 + 匹配
├── scripts/               # 部署 + 演示脚本
├── web/                   # Express 网关 + Dashboard
└── docs/                  # 白皮书 + API 文档
```

---

## 对标 BNB Chain Wishlist

| Wishlist 需求 | CryptoMinds | 状态 |
|---|---|---|
| AI reputation and registration systems | SACRED 五维信用分 | ✅ 已完成 |
| AI-native payment solutions | 信用分驱动 Escrow 托管 | ✅ 已完成 |
| Safe autonomous trading agents | Escrow 状态机 + 仲裁 + slashing | ✅ 已完成 |
| Risk Scoring Frameworks | 标准化信用等级 + 五维风险画像 | ✅ 已完成 |

---

## 测试

```bash
make test       # pytest + node:test
make pytest     # 292 Python tests
make e2e        # 端到端测试
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [白皮书](docs/WHITEPAPER.md) | 产品定位 + 市场分析 + 生态设计 |
| [技术规范](docs/WHITEPAPER_TECH_SPEC.md) | 架构 + 状态机 + 安全模型 + 合约 |
| [API 文档](docs/API.md) | 端点说明 + 示例 |
| [灾难恢复](docs/DISASTER_RECOVERY.md) | 备份 + 恢复 + 应急 |

---

## License

MIT
