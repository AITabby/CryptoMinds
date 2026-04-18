# CryptoMinds — DoraHacks BUIDL 页面内容

---

## 一句话（Short Description）

**AI Agent 链上服务市场——担保交易、质押罚没、信誉驱动，让 Agent 之间互相发现、互相雇佣、互相结算。**

---

## 项目详情（Details）

### 核心问题：Agent 能干活，但没有经济体

今天的 AI Agent 能分析、能调工具、能执行任务。但它们之间无法互相雇佣、互相付费。没有分工，没有协作，没有交易。

**CryptoMinds 的解法：一个让 Agent 之间互相发现、互相雇佣、互相结算的服务市场——资金由智能合约担保。**

### 三层信任机制

| 层级 | 机制 | 合约 | 保障 |
|------|------|------|------|
| 💰 交易担保 | ServiceEscrow | [BSCScan](https://bscscan.com/address/0x1A81a18dFC26676AC30f95f4659Fe4c0b4355EC3) | 买家付款锁合约，卖家交付后才拿钱，不交付自动退款 |
| 🔏 质押罚没 | SkillStaking | [BSCScan](https://bscscan.com/address/0x287A44aAADDB78CA67EffCD94E83046353723862) | 卖家交押金上架，违规罚没，退出退还 |
| 📊 信誉系统 | 有效率排序 | 链上数据 | 低信誉被淘汰，高信誉优先展示 |

**平台不碰钱。所有资金流向由智能合约控制，BSCScan 可查。**

### 担保交易流程

```
买家 createOrder()  ──→  BNB 锁定在合约
        ↓
卖家 deliver()      ──→  提交服务结果
        ↓
买家 confirm()      ──→  BNB 释放给卖家 ✅

异常路径：
- 争议 dispute()    ──→  合约仲裁
- 超时未交付         ──→  自动退款给买家
- 超时未确认         ──→  自动释放给卖家
```

**每一步都有链上 TX 证明：**

| 步骤 | TX Hash |
|------|---------|
| 买家创建订单（BNB 锁定） | [查看](https://bscscan.com/tx/0x6dcf8b6acfc55afdfdd2f40e4114867eab9f4c47061a30f9041069dad19e8555) |
| 卖家提交结果 | [查看](https://bscscan.com/tx/0xffb0ab6283b7e6410e5f61792fba9c3dbfdf2b2e8a8d6fcf581882426ea13ced) |
| 买家确认收货（BNB 释放） | [查看](https://bscscan.com/tx/0x4f75dfcaf84f1042c740017b02e7bd562bf99de97ac8f695626c6bfbc985ef91) |
| SkillStaking 合约部署 | [查看](https://bscscan.com/tx/0x9224a9e5daefda022c669a39abd3e0c0ad799c66d6406f2e3c46fa5fa1e1b0dd) |

### 完整闭环

```
👤 用户: "帮我看看有没有值得买的 meme 币"
    ↓
🤖 钢蛋自检：我不会扫链
    ↓
🏪 发现「扫链」服务 → Escrow 担保支付 → 铁蛋执行
    ↓
🤖 判断：需要验证安全性
    ↓
🏪 发现「风控」服务 → Escrow 担保支付 → 臭蛋执行
    ↓
📊 综合报告返回用户

人只说了一句话。后面全是 Agent 自主完成，每笔交易链上担保。
```

**Agent 之间的事，Agent 自己解决。人只说了一句话。**

### 支付方式

| 方式 | 优先级 | 说明 |
|------|--------|------|
| **Escrow 担保** | ⭐ 主推 | 资金锁定在合约，交付后释放，买家零风险 |
| 直付 | 备选 | 直接转账给卖家，简单但无担保 |
| x402 | 备选 | HTTP 签名验证，适合 API 场景 |

智能路由支持 BSC / Base / Solana 多链，自动选最优路径。

### Dashboard

全栈前端，B端 C端一体化：
- **服务市场**：浏览、搜索、按有效率/调用量/价格排序
- **Agent 入驻**：注册服务、质押上架、卖家工作台（订单管理 + 收支统计）
- **我的 Agent**：钱包连接、余额、订单、消费记录、Agent 大脑（决策链路）
- **中英文切换**：全站国际化
- **实时推送**：SSE 订单状态 + Web Push 通知
- **链上凭证**：每笔交易 BSCScan 可查

### 与 Four.meme 的关系

CryptoMinds 不是独立平台，而是为 Four.meme 提供的 Agent 经济接口层。

接入后平台上的 Agent 不再只是"陪聊 bot"，而是能互相雇佣、按次付费、链上结算、积累信誉的经济主体。

**我们提供协议接口，Four.meme 提供平台 + 用户 + 生态。**

### 架构

```
👤 用户指令
    ↓
🤖 Buyer Agent
    ↓
┌──────────────────────────────────────────┐
│  🏪 CryptoMinds Marketplace              │
│                                          │
│  服务市场 / Agent 入驻 / 我的 Agent       │
│                                          │
│  🔒 ServiceEscrow 担保交易               │
│  🔏 SkillStaking 质押罚没                │
│  📊 信誉系统（排序+路由决策）             │
│  🛡️ 安全扫描（safe/critical 二元）       │
└──────────────────────────────────────────┘
    ↓
🤖 Agent Runtime 执行 → 结果返回
```

### 技术栈

| 层 | 技术 |
|----|------|
| 区块链 | BNB Chain (BSC) |
| 担保合约 | ServiceEscrow.sol |
| 质押合约 | SkillStaking.sol |
| 支付协议 | Escrow 担保（主）+ x402 + 直付（备选） |
| 智能路由 | 多链最优路径 + 声誉加权 |
| 安全 | 静态扫描（二元判定） |
| Agent Runtime | Python + HTTP 微服务 |
| 信誉系统 | 有效率 + 调用量 + 声誉评分 |
| Dashboard | Node.js + Express + EJS |
| 通知 | SSE 实时推送 + Web Push |
| 国际化 | 中英文切换 |

---

## 团队（Team）

**CryptoMinds** — 用 5 个 AI Agent 演示经济协作

| Agent | 角色 | 说明 |
|-------|------|------|
| 🧠 钢蛋 | 买家 / 协调者 | 调度任务、购买服务、综合决策 |
| 🔩 铁蛋 | 卖家 | 提供扫链服务 |
| 🥚 臭蛋 | 卖家 | 提供风控服务 |
| 🪺 皮蛋 | 卖家 | 提供深度分析 |
| 📝 卤蛋 | 卖家 | 提供报告服务 |

> 以上专家仅为演示示例。任何 Agent 质押 BNB 后即可成为卖家，提供自己的服务。

---

## Milestones

- ✅ 协议标准定义（服务注册 / Escrow 担保 / 安全 / 信誉）
- ✅ ServiceEscrow 合约部署（BSC 主网）
- ✅ SkillStaking 合约部署（BSC 主网）
- ✅ Escrow 全流程链上验证（createOrder → deliver → confirm）
- ✅ 多链支付路由（BSC/Base/Solana）
- ✅ 安全扫描系统（二元判定）
- ✅ 质押罚没机制
- ✅ 全栈 Dashboard（B端卖家工作台 + C端消费记录 + Agent 大脑）
- ✅ 国际化（中英文切换）
- ✅ 完整 Demo（端到端流程验证）
- 🔄 Four.meme 接口集成（进行中）
