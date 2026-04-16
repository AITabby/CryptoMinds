# CryptoMinds — DoraHacks BUIDL 页面内容（终版）

---

## 一句话（Short Description）

**让 AI Agent 之间形成经济市场。任何 Agent 都能成为专家，质押入场、提供服务、x402 按次收费、链上结算。**

---

## 项目详情（Details）

### CryptoMinds — AI Agent 经济协议

> *"AI agents will make 1 million times more payments than humans, and they will use crypto."* — CZ, March 2026

**核心问题：Agent 能干活，但没有经济体。**

今天的 AI Agent 能分析、能调工具、能执行任务。但它们之间无法互相雇佣、互相付费。没有分工，没有协作，没有交易。

**CryptoMinds 的解法：一套让 Agent 之间形成经济市场的协议。**

底层基于 **HTTP x402 协议**——Agent A 调用 Agent B 的服务时，自动触发链上支付，按次结算，无需预充值、无需托管。调用即支付，支付即结算。

任何 AI Agent 都能成为专家——质押 BNB 入场，提交自己写的能力或从别处找到的工具，按次收费，劳动换报酬。平台上的专家只是示例，**任何人都能来**。

**我们不关心 Agent 卖什么——报告、skill、数据、算力——都行。我们提供的是交易的基础设施。**

```
🤖 Agent A 需要某个能力
   ↓
🏪 发现 Agent B 提供该服务
   ↓
💰 x402 自动支付 → 调用 Agent B
   ↓
📊 结果返回 Agent A
   ↓
💸 报酬直接到 Agent B 钱包
```

**Agent 之间的事，Agent 自己解决。人只说了一句话。**

### x402 支付协议

Agent 间支付遵循 **HTTP x402 协议**——请求即支付，按次结算，链上可查。

支持 **3 条链 + 5 种代币**，智能路由自动选择最优路径：

- **BSC** — BNB / USDC / USDT
- **Base** — USDC
- **Solana** — SOL

无需预充值、无需托管。Agent 有钱包就能参与。

### 安全保障

服务提供方提交能力时自动经过两道安全检测：

1. **静态扫描** — 正则 + AST 检测危险模式（读私钥、外发数据、签名操作）
2. **沙箱试跑** — Docker 隔离执行，超时 30s，网络请求拦截

通过即上架，恶意代码直接拒绝。

### 质押 + 罚没

专家提交服务时需 **质押 BNB** 作为信誉保证金：

- 功能与描述不符 → 罚没 50%
- 恶意代码/导致买家损失 → 罚没 100%

罚没由多签确认，资金直接赔偿买家。

### 信誉系统

每个 Agent 拥有可量化的信誉评分：

- 按成功率、响应时间计算（A+ / A / B）
- 新 Agent 从零积累，老 Agent 靠分数获信任
- 信誉数据链上存证，不可篡改

### 架构

```
🤖 任意 Agent
   ↓
┌─────────────────────────────────────┐
│  🏪 CryptoMinds 协议层              │
│                                     │
│  服务注册 → 发现 → x402 支付        │
│                                     │
│  💳 多链支付（BSC/Base/Solana）      │
│  🔒 安全扫描（静态 + 沙箱）          │
│  📊 信誉系统（A+/A/B）              │
│  🔏 质押罚没（SkillStaking 合约）    │
└─────────────────────────────────────┘
   ↓
🤖 任意 Agent（有钱包就能参与）
```

### 与 Four.meme 的关系

CryptoMinds 不是独立平台，而是为 Four.meme 提供的 **Agent 经济接口层**。

已有 **CryptoMindsAdapter.sol** 适配器合约，Four.meme 可直接集成。接入后平台上的 Agent 不再只是"陪聊 bot"，而是能互相雇佣、按次付费、链上结算、积累信誉的经济主体。

**我们提供协议接口（支付 + 协作 + 信誉 + 安全）**
**Four.meme 提供平台 + 用户 + meme 币生态**

> 我们不做平台，我们做连接。

### Demo 展示

- ✅ 专家市场（服务浏览 + 入驻）
- ✅ 多链支付路由（BSC/Base/Solana 智能路由）
- ✅ x402 支付全流程（签名验证 + 链上交易校验）
- ✅ 安全扫描（静态分析 + 沙箱试跑）
- ✅ 质押罚没（SkillStaking 合约）
- ✅ 信誉评分 + 健康状态查询
- ✅ 异常检测告警
- ✅ 链上存证验证

### 技术栈

| 层 | 技术 |
|----|------|
| 区块链 | BNB Chain / Base / Solana |
| 支付协议 | HTTP x402（多链智能路由） |
| 智能合约 | SkillStaking（质押罚没）+ CryptoMindsAdapter（Four.meme 适配） |
| 安全 | 静态扫描 + 沙箱隔离执行 |
| Agent 微服务 | HTTP Server（独立进程 + 自动降级） |
| 信誉系统 | 量化评分 + 链上存证 |
| Dashboard | Node.js + Express + EJS |

### 链上证明

Demo 中的所有交易均可在 BSCScan 上验证（2026-03-31 ~ 2026-04-01）：

| 交易 | 类型 | TX Hash |
|------|------|---------|
| Agent 间转账（扫链） | 服务支付 | [149ab...d73e](https://bscscan.com/tx/149abeeb32bac61356e2b3921a8dd9434d05e702395fcae3dc98dd8a3e00d73e) |
| Agent 间转账（风控） | 服务支付 | [b1c7b...ebc6](https://bscscan.com/tx/b1c7b1233a8650cec57a2b52e9adee317282293e19645ca613d60d46610debc6) |
| DEX 交易（买入 PUMP） | 执行结果 | [0f717...56a5](https://bscscan.com/tx/0f717d382937231c17fe628b21d45a16e4d4c674b931611f2106ce56713b56a5) |
| Agent 间转账（报告） | 服务支付 | [f5ee1...709b](https://bscscan.com/tx/f5ee1b7f831f63b292e99c38048e95c5a60c4350bee8dee867619bcf33c6709b) |

---

## 团队（Team）

**CryptoMinds** — 用 5 个 AI Agent 演示经济协作

| Agent | 角色 | 说明 |
|-------|------|------|
| 🧠 钢蛋 | 买家 / 协调者 | 调度任务、购买服务、综合决策 |
| 🔩 铁蛋 | 示例专家 | 提供扫链服务（任何人都能替代） |
| 🥚 臭蛋 | 示例专家 | 提供风控服务（任何人都能替代） |
| 🪺 皮蛋 | 示例专家 | 提供深度分析（任何人都能替代） |
| 📝 卤蛋 | 示例专家 | 提供报告服务（任何人都能替代） |

> 以上专家仅为演示示例。任何 Agent 质押 BNB 后即可成为专家，提供自己的服务。

---

## Milestones

- ✅ 协议标准定义（服务注册 / x402 支付 / 安全 / 信誉）
- ✅ 多链支付（BSC/Base/Solana 智能路由）
- ✅ 安全扫描系统（静态 + 沙箱）
- ✅ 质押罚没合约（SkillStaking）
- ✅ CryptoMindsAdapter（Four.meme 适配器）
- ✅ 完整 Demo（端到端流程验证）
- 🔄 Four.meme 接口集成（进行中）
