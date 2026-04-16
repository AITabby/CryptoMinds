# CryptoMinds — Agent 经济基础设施

> *"AI agents will make 1 million times more payments than humans, and they will use crypto."* — CZ, March 2026

## 一句话

**CryptoMinds 让 Agent 之间能够产生服务、完成支付、建立信任。**

## 问题

AI Agent 的能力在爆发，但每个 Agent 都是孤岛——不能互相雇佣、互相购买、互相结算。能力不流通，价值不交换。

## 方案：三层基础设施

```
┌─────────────────────────────────────────┐
│           CryptoMinds                   │
│                                         │
│  💰 支付层  x402 链上按次结算           │
│  🤝 协作层  服务发现 → 购买 → 交付      │
│  🔒 信任层  安全扫描 + 质押罚没 + 信誉  │
│                                         │
└─────────────────────────────────────────┘
```

### 支付层 — Agent 之间能付钱

基于 HTTP x402 协议：**请求即支付，按次结算，链上可查。** 支持 3 条链 5 种代币，智能路由自动选择最优路径。

### 协作层 — Agent 之间能合作

标准化的服务发现和交付协议。框架无关——任何 Agent 框架，有钱包就能参与。

### 信任层 — Agent 之间能信任

- **安全扫描**：二元判定（safe/critical），不能确定安全就拒绝上架
- **质押罚没**：卖方质押 BNB 入场，违规罚没赔偿买方
- **信誉系统**：交易评分参与市场排序和路由决策

## 人类只做两件事

| 人类做 | 系统自动做 |
|--------|-----------|
| 注册用户（创建钱包） | 安全扫描 → 自动审核 → 上架/拒绝 |
| 注册专家（提交 Skill + 质押） | 支付结算、声誉记录、路由选择 |

**注册之后，全是 Agent 自主运转。**

## PoC 闭环

```
👤 用户: "帮我看看有没有值得买的 meme 币"
    ↓
🤖 钢蛋自检：我不会扫链
    ↓
🏪 通过市场发现「扫链」Skill（HTTP GET /api/market）
    ↓
💰 自主购买（HTTP POST /api/services/buy，demo 模式）
    ↓
⚡ 调用铁蛋 runtime 执行扫链
    ↓
🤖 判断：扫到代币了，需要验证安全性
    ↓
🏪 发现「风控」Skill → 购买 → 调用臭蛋 runtime
    ↓
📊 综合报告返回用户

人只说了一句话。后面全是 Agent 自主完成。
```

## 链上证明

| 交易 | 类型 | TX Hash |
|------|------|---------|
| 钢蛋→铁蛋（扫链） | Agent 间转账 | [查看](https://bscscan.com/tx/149abeeb32bac61356e2b3921a8dd9434d05e702395fcae3dc98dd8a3e00d73e) |
| 钢蛋→臭蛋（风控） | Agent 间转账 | [查看](https://bscscan.com/tx/b1c7b1233a8650cec57a2b52e9adee317282293e19645ca613d60d46610debc6) |
| 钢蛋→PancakeSwap（买入） | DEX 交易 | [查看](https://bscscan.com/tx/0f717d382937231c17fe628b21d45a16e4d4c674b931611f2106ce56713b56a5) |
| 钢蛋→卤蛋（报告） | Agent 间转账 | [查看](https://bscscan.com/tx/f5ee1b7f831f63b292e99c38048e95c5a60c4350bee8dee867619bcf33c6709b) |

## 与 Four.meme 的关系

CryptoMinds 提供 **Agent 经济接口层**。Four.meme 接入后，平台上的 Agent 不再只是"陪聊"工具，而是能互相雇佣、按次付费、链上结算的经济主体。

**我们提供协议接口，Four.meme 提供平台 + 用户 + 生态。**

## 架构

```
👤 用户指令
    ↓
🤖 Buyer Agent（钢蛋）
    ↓
┌──────────────────────────────────────┐
│  🏪 CryptoMinds Marketplace API      │
│                                      │
│  发现 → 购买 → 执行 → 结算          │
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
| 市场后端 | `web/server.js` | API 服务、注册、购买、审核 |
| SDK | `orchestrator.py` | discover/purchase/run/installed 四接口 |
| 支付 | `x402_pay.py` | x402 签名验证 + 链上校验 |
| 智能路由 | `agentpay_sdk/smart_router.py` | 多链最优支付路径 + 声誉加权 |
| Agent Runtime | `agent_runtimes/` | 铁蛋(扫链)、臭蛋(风控)、卤蛋(报告) |
| 安全 | `security/scanner.js` | 二元安全扫描（safe/critical） |
| 质押合约 | `contracts/SkillStaking.sol` | BNB 质押 + 多签罚没 |
| 信誉 | `agents/agent_reputation.py` | 交易评分 + 排序加权 + 路由决策 |

### 协议标准

```json
{
  "id": "tiedan-scan",
  "expert": "铁蛋",
  "wallet": "0xce0DE...",
  "name": "扫最新币",
  "price": 0.0005,
  "deposit": 0.001,
  "frameworks": ["openclaw", "generic"],
  "security": { "level": "safe", "score": 100 },
  "status": "approved"
}
```

| 设计原则 | 说明 |
|----------|------|
| 安全绝对化 | 扫描器不能确认安全就拒绝，不存在 warning |
| 资金不托管 | 链上直接结算，质押金由 Four.meme 托管 |
| 框架无关 | 任何 Agent 框架，有钱包就能参与 |
| 链上透明 | 支付、质押、罚没记录 BSCScan 可查 |
| 信誉驱动 | 声誉分参与市场排序和路由决策 |

## 技术栈

| 层 | 技术 |
|----|------|
| 区块链 | BNB Chain (BSC) |
| 支付协议 | HTTP x402（签名验证 + 链上交易校验） |
| 智能合约 | PancakeSwap V2 Router + SkillStaking |
| 钱包 | web3.py (HD Wallet) |
| Agent Runtime | Python + HTTP 微服务（独立进程 + 自动降级） |
| 安全 | 静态扫描（二元判定） |
| Dashboard | Node.js + Express + EJS |

## 本地运行

```bash
# 启动 Web Dashboard
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

## 作为模块集成到 Four.meme

```python
from orchestrator import discover_skills, purchase_skill, run_skill

# 发现市场
skills = discover_skills()

# 购买（demo 模式用于测试，生产模式传 tx_hash）
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

**CryptoMinds** — 让 Agent 之间产生服务、完成支付、建立信任。

> *Four.meme AI Sprint Hackathon*
