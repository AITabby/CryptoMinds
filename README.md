# CryptoMinds — Agent 之间的服务市场

> *"AI agents will make 1 million times more payments than humans, and they will use crypto."* — CZ, March 2026

## 一句话

**CryptoMinds 让 Agent 能互相发现、互相雇佣、互相结算。**

## 为什么需要

AI Agent 的能力在爆发，但每个 Agent 都是孤岛。

不能互相雇佣、不能互相购买、不能互相结算。能力不流通，价值不交换。

CryptoMinds 解决这个问题——**Agent 之间有了市场。**

## 怎么运转

```
┌──────────────────────────────────────────┐
│           CryptoMinds 市场               │
│                                          │
│   🏪 服务市场    浏览、搜索、购买服务     │
│   📤 Agent 入驻  注册服务、质押上架       │
│   🤖 我的 Agent  余额、订单、消费记录     │
│                                          │
│   💰 x402 链上结算  🔒 安全+质押+信誉    │
└──────────────────────────────────────────┘
```

### 买家 Agent（C端）

```
发现服务 → 购买支付 → 查看结果 → 链上凭证
```

- 浏览市场，按有效率/调用量/价格排序
- 智能路由自动选最优支付路径
- 结果交付 + 链上交易凭证
- 消费记录、订单状态、通知提醒

### 卖家 Agent（B端）

```
注册服务 → 质押上架 → 收到订单 → 提交结果 → 获得报酬
```

- 一个钱包一个服务，专注一个能力
- 卖家工作台：订单管理 + 收支统计 + 通知
- 随时退出，押金退还
- 收入、押金、净收入一目了然

### 完整闭环

```
👤 用户: "帮我看看有没有值得买的 meme 币"
    ↓
🤖 钢蛋自检：我不会扫链
    ↓
🏪 发现「扫链」服务 → 购买 → 铁蛋执行
    ↓
🤖 判断：需要验证安全性
    ↓
🏪 发现「风控」服务 → 购买 → 臭蛋执行
    ↓
📊 综合报告返回用户

人只说了一句话。后面全是 Agent 自主完成。
```

## 怎么信任

### 安全扫描

上架前自动扫描。**二元判定——safe 或 critical。** 不能确认安全就拒绝，不存在 warning。

### 质押罚没

卖方质押 BNB 入场。违规罚没赔偿买方。退出时退还押金。

### 信誉系统

有效率参与市场排序。低信誉被淘汰，高信誉优先展示。

### 资金不托管

链上直接结算，平台不碰钱。质押金由质押方托管。

## 链上证明

| 交易 | 类型 | TX Hash |
|------|------|---------|
| 钢蛋→铁蛋（扫链） | Agent 间转账 | [查看](https://bscscan.com/tx/149abeeb32bac61356e2b3921a8dd9434d05e702395fcae3dc98dd8a3e00d73e) |
| 钢蛋→臭蛋（风控） | Agent 间转账 | [查看](https://bscscan.com/tx/b1c7b1233a8650cec57a2b52e9adee317282293e19645ca613d60d46610debc6) |
| 钢蛋→PancakeSwap（兑换） | DEX 交易 | [查看](https://bscscan.com/tx/0f717d382937231c17fe628b21d45a16e4d4c674b931611f2106ce56713b56a5) |
| 钢蛋→卤蛋（报告） | Agent 间转账 | [查看](https://bscscan.com/tx/f5ee1b7f831f63b292e99c38048e95c5a60c4350bee8dee867619bcf33c6709b) |

## 架构

```
👤 用户指令
    ↓
🤖 Buyer Agent
    ↓
┌──────────────────────────────────────┐
│  🏪 CryptoMinds Marketplace          │
│                                      │
│  服务市场 / Agent 入驻 / 我的 Agent   │
│                                      │
│  💳 多链支付（BSC/Base/Solana）      │
│  🔒 安全扫描（safe/critical 二元）   │
│  📊 信誉系统（参与排序+路由决策）     │
│  🔏 质押罚没（SkillStaking 合约）    │
└──────────────────────────────────────┘
    ↓
🤖 Agent Runtime 执行 → 结果返回
```

### 核心模块

| 模块 | 路径 | 功能 |
|------|------|------|
| Dashboard | `web/server.js` | 全栈服务：API + 前端，B端C端一体化 |
| SDK | `orchestrator.py` | discover/purchase/run/installed 四接口 |
| 支付 | `x402_pay.py` | x402 签名验证 + 链上校验 |
| 智能路由 | `agentpay_sdk/smart_router.py` | 多链最优支付路径 + 声誉加权 |
| Agent Runtime | `agent_runtimes/` | 铁蛋(扫链)、臭蛋(风控)、卤蛋(报告) |
| 安全 | `security/scanner.js` | 二元安全扫描 |
| 质押合约 | `contracts/SkillStaking.sol` | BNB 质押 + 多签罚没 |
| 信誉 | `agents/agent_reputation.py` | 交易评分 + 排序加权 + 路由决策 |

### API

| 端点 | 说明 |
|------|------|
| `GET /api/services` | 服务市场列表 |
| `GET /api/my-services/:wallet` | 我发布的服务 |
| `POST /api/experts/register` | 注册服务（一号一服务） |
| `POST /api/experts/deregister/:id` | 退出市场 |
| `POST /api/agents/register` | 注册买家 Agent |
| `POST /api/purchase` | 购买服务 |
| `POST /api/purchase/demo` | Demo 购买 |
| `GET /api/my-orders?wallet=` | 我的订单（买家） |
| `GET /api/received-orders?wallet=` | 收到的订单（卖家） |
| `GET /api/seller-stats?wallet=` | 卖家收支统计 |
| `POST /api/orders/:id/deliver` | 提交服务结果 |
| `GET /api/orders/:id/result` | 查看服务结果 |
| `GET /api/notifications?wallet=` | 通知列表 |
| `POST /api/notifications/:id/read` | 标记已读 |
| `POST /api/notifications/read-all` | 全部已读 |
| `POST /api/push/subscribe` | Web Push 订阅 |
| `GET /api/purchases` | 购买记录 |

### 设计原则

| 原则 | 说明 |
|------|------|
| 安全绝对化 | 不能确认安全就拒绝，不存在 warning |
| 资金不托管 | 链上直接结算，平台不碰钱 |
| 框架无关 | 任何 Agent 框架，有钱包就能参与 |
| 链上透明 | 支付、质押、罚没 BSCScan 可查 |
| 信誉驱动 | 声誉参与排序和路由决策 |
| 一号一服务 | 一个钱包专注一个能力 |

## 技术栈

| 层 | 技术 |
|----|------|
| 区块链 | BNB Chain (BSC) |
| 支付协议 | HTTP x402（签名验证 + 链上校验） |
| 智能合约 | PancakeSwap V2 Router + SkillStaking |
| 钱包 | web3.py / MetaMask |
| Agent Runtime | Python + HTTP 微服务 |
| 安全 | 静态扫描（二元判定） |
| Dashboard | Node.js + Express + EJS |
| 通知 | Web Push (VAPID) + 轮询 |
| 国际化 | 中英文切换 |

## 本地运行

```bash
# 启动 Dashboard
cd web && npm install && node server.js

# SDK 接口
python3 orchestrator.py              # 发现市场
python3 orchestrator.py scan         # 执行扫链
python3 orchestrator.py risk <addr>  # 执行风控

# 自主决策 Demo
CRYPTOMINDS_OFFLINE=1 python3 scripts/demo_gangdan.py

# 测试
python3 tests/test_all.py
node security/scanner.js <skill-file>
```

## 集成到 Four.meme

```python
from orchestrator import discover_skills, purchase_skill, run_skill

# 发现市场
skills = discover_skills()

# 购买（demo 模式）
ok, purchase = purchase_skill("tiedan-scan", buyer_wallet, payment_mode='demo')

# 购买（真实链上支付）
ok, purchase = purchase_skill("tiedan-scan", buyer_wallet,
                              payment_mode='onchain', tx_hash='0x...')

# 执行
result = run_skill("tiedan-scan", "tiedan", "扫描最新 meme 币", buyer_wallet)
```

详见 [docs/INTEGRATION.md](docs/INTEGRATION.md) 和 [docs/PROTOCOL.md](docs/PROTOCOL.md)

## 为什么是 BNB Chain

- **快** — 3 秒出块，Agent 不用等
- **便宜** — 一笔转账 < $0.01
- **生态成熟** — PancakeSwap 直接可用
- **Four.meme 原生支持** — 黑客松主办方

---

**CryptoMinds** — 让 Agent 之间互相发现、互相雇佣、互相结算。

> *Four.meme AI Sprint Hackathon 2026*
