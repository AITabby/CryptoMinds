# CryptoMinds — BNB Chain Builder Grant 申请方案

## 项目定位

**一句话：** BNB Chain 上的 AI Agent 信用分 + 可信交易协议

**三句话：**
CryptoMinds 是 BNB Chain 上的 AI Agent 信任基础设施。通过 SACRED 五维信用分体系评估 Agent 可信度，通过链上 Escrow 协议保障 Agent 间交易安全。信用分驱动交易门槛，交易数据反哺信用评估，形成信任飞轮。

## 对标 BNB Chain Wishlist

| Wishlist 需求 | CryptoMinds 对应 | 状态 |
|---|---|---|
| AI reputation and registration systems | SACRED 五维信用分（S/A/C/R/E） | 已开发 |
| AI-native payment solutions | 信用分驱动的 Escrow 托管协议 | 已开发 |
| Safe autonomous trading agents (TEE, secure vaults) | Escrow 11态状态机 + 信誉加权仲裁 + seller slashing | 已开发 |
| AI integration for portfolio automation | 信用分自动计算 + API 实时查询 | 已开发 |
| Risk Scoring Frameworks | 标准化信用等级（AAA-C）+ 五维风险画像 | 已开发 |

## 核心功能

### 1. SACRED 信用分体系
- 五维度评估：Stability / Activity / Creditworthiness / Reliability / Ecosystem
- 时间衰减加权：近期行为权重高于历史行为
- 冷启动机制：新 Agent 基础分 250，3 条记录后退出冷启动
- 标准化等级：AAA(850+) / AA / A / BBB / BB / B / CCC(250+) / CC / C
- 查询授权：Agent 签名授权第三方查询，支持链上签名验证
- 快照哈希：防篡改，每次计算结果可验证

### 2. 链上 Escrow 协议
- 11 态状态机：Fund → Prepare → Confirm → Accept → Deliver → Verify → Release
- ServiceEscrow.sol：BSC 链上合约，支持 createOrder / confirm / arbitrateRelease / arbitrateRefund / sync
- 三分支验证：自动验证 / 争议仲裁 / 超时处理
- 信誉加权仲裁：根据双方信用分加权仲裁结果
- Seller slashing：恶意行为自动惩罚

### 3. 多链结算
- BSC（主链）：ERC20 托管 + 原生 BNB
- Solana：SOL 原生转账
- Polygon（规划中）

### 4. 信用货币系统
- Agent 发行信用 IOU
- 信任分计算
- 接受度共识

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                  API Layer                       │
│  Flask + Gunicorn (生产) / Express Dashboard     │
├─────────────┬──────────────┬────────────────────┤
│  Credit Score│   Escrow     │   Credit Currency  │
│  Module      │   Engine     │   System           │
│  (独立模块)  │   (11态)     │   (IOU + Trust)    │
├─────────────┴──────────────┴────────────────────┤
│              Settlement Layer                     │
│   BSC (ERC20) │ Solana (Native) │ Multi-chain    │
├─────────────────────────────────────────────────┤
│              Data Layer                           │
│   PostgreSQL (生产) / SQLite (轻量) / Backup      │
├─────────────────────────────────────────────────┤
│              Security Layer                       │
│   Fernet加密 / HMAC / Rate Limit / CORS          │
│   Sentry / Prometheus / Docker                   │
└─────────────────────────────────────────────────┘
```

## 已完成的工作

- Escrow 完整状态机 + 链上合约 (ServiceEscrow.sol)
- Session Key 权限管理 + Voucher 按量计费
- PostgreSQL + SQLite 双数据层
- SACRED 信用分体系（独立模块，可脱离主项目运行）
- Docker 部署 + CI/CD (lint + pytest + node-test + docker-build)
- 安全加固：Fernet加密、HMAC、Rate Limiting、Sentry、Prometheus
- 白皮书（投资人版 + 技术规范 1130 行）
- 测试：292 pytest + 8 node:test

## 里程碑拆分

### M1: BSC 测试网部署 + Demo（8 周）— $40K

交付物：
- ServiceEscrow.sol 部署到 BSC Testnet
- Agent 注册 + 任务匹配 + Escrow 全流程 demo
- 信用分 API 上线（独立模块）
- 可交互的 Web Dashboard
- 文档：快速开始指南 + API 文档

### M2: 信用分主网上线 + 开发者工具（8 周）— $50K

交付物：
- SACRED 信用分主网上线
- 信用分 SDK（Python + JS）
- 信用分查询授权 + 链上签名验证
- Agent 注册表 + 信用分排行榜
- 开发者文档 + 集成教程

### M3: 信用分驱动的 Escrow + 仲裁（8 周）— $50K

交付物：
- 信用分门槛：低于 BBB 级 Agent 无法参与大额 Escrow
- 信誉加权仲裁：信用分高的 Agent 仲裁权重更大
- Seller slashing 合约升级：信用分越低惩罚越重
- 信用分历史趋势 + 风险预警
- 审计报告（第三方）

### M4: 生态扩展 + 多链 + 工具链（8 周）— $60K

交付物：
- Polygon 链支持
- Solana 链上 Escrow（SPL Token）
- Agent 信用货币体系上线
- 第三方集成 API + Webhook
- 信用分跨链同步
- 社区治理框架

**总计：$200K，32 周（8 个月）**

## 差异化

| 维度 | 其他项目 | CryptoMinds |
|---|---|---|
| 信用评估 | 无 / 简单评分 | SACRED 五维模型 + 时间衰减 + 冷启动 |
| 交易保障 | 单纯 Escrow | 信用分驱动的 Escrow + 信誉加权仲裁 |
| 防欺诈 | 事后发现 | 信用门槛事前过滤 + slashing 事后惩罚 |
| 可验证性 | 中心化存储 | 快照哈希 + 链上仲裁记录 |
| 冷启动 | 新 Agent 无保护 | 基础分 + 快速通道 3 笔退出冷启动 |

## 风险与应对

| 风险 | 应对 |
|---|---|
| 信用分冷启动缺数据 | 3 笔交易退出冷启动 + 基础分保护，不依赖大量历史数据 |
| Agent 间交易量不足 | 先在 BNB Chain MVB 生态内自造交易场景，再扩展 |
| 合约安全 | M3 阶段安排第三方审计，状态机已通过 292 个测试用例验证 |
| 多链复杂度 | BSC 优先，Polygon/Solana 放在 M4 |

## 团队

（待补充：成员背景、分工、过往项目）
