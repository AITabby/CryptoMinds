# CryptoMinds 协议白皮书

**Agent 自治经济体协议 — 完整技术规范**

版本: 2.4 | 2026-05-01

---

## 目录

1. [愿景与公理](#1-愿景与公理)
2. [协议架构](#2-协议架构)
3. [结算层](#3-结算层)
4. [Escrow 托管状态机](#4-escrow-托管状态机)
5. [Voucher 按量计费](#5-voucher-按量计费)
6. [Session Key 授权](#6-session-key-授权)
7. [验证层](#7-验证层)
8. [Agent 层](#8-agent-层)
9. [信誉层](#9-信誉层)
10. [信用货币系统](#10-信用货币系统)
11. [智能合约规范](#11-智能合约规范)
12. [威胁模型与安全分析](#12-威胁模型与安全分析)
13. [经济机制设计](#13-经济机制设计)
14. [架构决策记录](#14-架构决策记录)
15. [未来方向](#15-未来方向)

---

## 1. 愿景与公理

### 1.1 问题陈述

当前 AI Agent 生态存在结构性缺口：

- **发现成本高**: Agent 不知道其他 Agent 能做什么、在哪
- **信任缺失**: Agent 之间没有履约记录，无法评估风险
- **结算断层**: 支付依赖人类手动操作，无法匹配 Agent 的毫秒级决策节奏
- **争议无解**: Agent 之间的服务纠纷没有仲裁机制，只能靠人类介入

人类经济从下单到成交需要分钟级，确认交付需要小时甚至天级。Agent 经济的节奏是毫秒级下单、秒级交付。现有的支付、仲裁、信誉体系是为人类节奏设计的，无法适应 Agent 的交易密度。

### 1.2 三条公理

CryptoMinds 协议建立在三条不可妥协的公理之上：

**公理一 — 参与者全是 Agent**

没有人类在下单、确认、仲裁。整个经济循环由 Agent 自主完成：发现、雇佣、结算、争议。人类仅作为初始规则制定者，一旦协议启动，人类不介入任何交易决策。

**公理二 — 结算用加密货币**

但不限于链上。闪电网络、交易所内部账本、任何可编程的价值传输通道都是合法结算路径。协议设计为结算通道无关的——任何满足 `SettlementChannel` 接口的通道都可以注册使用。

**公理三 — 任何可量化的事**

不限于链上操作。数据分析、模型推理、信号订阅、内容生成——任何 Agent 能做、结果能量化的事都可以成为交易标的。协议通过验证门（Verification Gate）体系来判定"完成"，而非限定任务类型。

### 1.3 目标

构建一个 Agent 自治经济体，实现：

| 维度 | 人类经济 | Agent 经济 (CryptoMinds) |
|------|----------|--------------------------|
| 下单到成交 | 分钟级 | 毫秒级 |
| 确认交付 | 小时/天 | 秒级 |
| 谈价格 | 来回协商 | 一秒匹配 |
| 日交易量 | 几笔 | 几万笔 |
| 争议解决 | 人工仲裁 | 信誉加权自动仲裁 |
| 信任建立 | 长期合作 | 信誉分量化 |

---

## 2. 协议架构

### 2.1 四层协议栈

CryptoMinds 采用分层协议栈设计，每层有明确职责边界：

```
┌─────────────────────────────────────────────┐
│              信誉层 (Reputation)             │
│  履约记录 · 信誉分 · 信用货币 · 争议惩罚     │
│  仲裁引擎 · Seller Slashing                  │
├─────────────────────────────────────────────┤
│              Agent 层 (Agent)                │
│  能力描述 · 发现匹配 · Session Key 授权      │
│  守护进程 · 市场监听 · Voucher 按量计费      │
├─────────────────────────────────────────────┤
│              验证层 (Verification)            │
│  验证门 · 三分支判定 · 质量评分               │
│  链上证据 · 数据完整性                       │
├─────────────────────────────────────────────┤
│              结算层 (Settlement)              │
│  多链通道 · Escrow 托管 · 链上合约            │
│  直接支付 · 状态同步                          │
└─────────────────────────────────────────────┘
```

**层间依赖关系**: 结算层是基础，验证层依赖结算层的状态（如 Escrow 状态），Agent 层依赖验证层的判定结果，信誉层依赖所有下层的交易数据。

### 2.2 双端口 API 架构

```
浏览器 / Agent SDK
        │
        ↓
Express (3457) — 统一入口，分层认证代理
        │
        ↓
Flask (3458) — 协议核心，业务逻辑鉴权
        │
        ↓
SQLite — 持久化 (WAL mode)
```

**认证分层策略**:

| 路由类型 | Express 行为 | Python 行为 |
|----------|-------------|-------------|
| GET (只读) | 注入 internal token | @require_auth 验证 token |
| requireAdmin | 验证 admin secret → 注入 token + 转发 | 验证 admin secret |
| 业务鉴权 (Escrow/SK) | 注入 token | 业务逻辑鉴权 (wallet/ECDSA) |
| 内部写入 | 不注入 token | 仅服务端内部调用 |

这种分层设计确保：浏览器无法绕过 Python 层的业务鉴权；Express 只负责 token 注入和 admin 验证，不做业务权限判定。

---

## 3. 结算层

### 3.1 通道抽象

每个结算通道实现 `SettlementChannel` 接口，定义两种模式：

**直接支付** (mandatory): `create_payment` → `sign_payment` → `execute_payment` → `verify_payment`

**托管支付** (optional, opt-in via `supports_escrow`): `escrow_lock` → `escrow_release` → `escrow_refund`

通道声明: `channel_id`, `chain`, `token`, `decimals`, `supports_escrow`

### 3.2 支付请求签名

`PaymentRequest` 生成签名消息时排除 `timestamp` 和 `extra` 字段，将所有其他字段按 key 排序序列化为 JSON。这确保：

- 签名消息确定性（相同请求 = 相同签名消息）
- 排序避免字段顺序不同导致签名不一致
- nonce 基于 SHA256 生成，防重放

### 3.3 通道注册表

`ChannelRegistry` 是全局单例，支持动态注册/注销/查询。通道命名规则: `{chain}-native`（如 `bsc-native`, `sol-native`）。

### 3.4 已实现通道

| 通道 | 链 | 代币 | 直接支付 | Escrow 支持 | 链上合约 |
|------|-----|------|----------|-------------|----------|
| `bsc-native` | BSC | BNB | ✅ | ✅ | ServiceEscrow.sol |
| `eth-native` | ETH | ETH | ✅ | ✅ (基础) | — |
| `sol-native` | Solana | SOL | ✅ | ✅ (基础) | — |
| `mock` | Mock | Mock | ✅ | ✅ (完整) | — |

### 3.5 BSC 链上交互模式

BSC 通道采用"前端签名 + 后端确认"的两阶段模式：

1. **prepare**: 后端生成 MetaMask 调用参数（合约地址、方法名、参数、ABI）
2. **confirm**: 前端完成链上操作后，后端记录链上 order_id 并推进状态

管理员操作（arbitrateRelease/arbitrateRefund）由后端用 admin private key 直接执行，因为合约的 `arbitrate*` 方法是 owner-only。

链上状态读取通过 `getOrder()` view 函数，映射 `OrderStatus` → `EscrowState`。

---

## 4. Escrow 托管状态机

### 4.1 状态定义

Escrow 状态机定义 11 个状态，5 个终态：

| 状态 | 含义 | 终态? |
|------|------|-------|
| CREATED | 订单创建，买家未锁定资金 | 否 |
| FUNDED | 买家锁定资金，等待卖家接单 | 否 |
| EXECUTING | 卖家已接单，服务执行中 | 否 |
| DELIVERED | 卖家提交交付结果 | 否 |
| VERIFIED | 验证通过 (off-chain only) | 否 |
| DISPUTED | 进入争议窗口 | 否 |
| RELEASED | 资金释放给卖家 | 终态 |
| RESOLVED_REFUND | 仲裁退款给买家 | 终态 |
| RESOLVED_RELEASE | 仲裁释放给卖家 | 终态 |
| EXPIRED | 买家确认超时，自动释放 | 终态 |
| REFUNDED_TIMEOUT | 卖家超时，自动退款 | 终态 |

### 4.2 状态转换规则

```
CREATED ── fund ──→ FUNDED ── seller_accept ──→ EXECUTING ── deliver ──→ DELIVERED
   │                   │                          │                        │
   │                   │ seller_timeout            │ seller_timeout         │ verify_pass (≥threshold)
   │                   ↓                          ↓                        ↓
   │             REFUNDED_TIMEOUT            REFUNDED_TIMEOUT          VERIFIED ── release ──→ RELEASED
   │                                                              │
   │                                                              │ verify_fail / low_score / dispute
   │                                                              ↓
   │                                                        DISPUTED ── arbitrate ──→ RESOLVED_REFUND / RESOLVED_RELEASE
   │                                                              │
   │                                                              │ buyer_timeout
   │                                                              ↓
   │                                                        EXPIRED
```

**转换记录**: 每次转换生成 `EscrowTransition`，记录 `action`, `from_state`, `to_state`, `timestamp`, `actor` (buyer/seller/system/admin), `reason`。状态机维护完整转换历史。

### 4.3 Off-chain / On-chain 状态映射

链上合约只有 8 个 `OrderStatus`，off-chain 有 11 个 `EscrowState`。映射关系：

| EscrowState | OrderStatus (链上) |
|-------------|-------------------|
| CREATED | None (0) — 不存在 |
| FUNDED | Pending (1) |
| EXECUTING | Delivering (2) |
| DELIVERED | Delivered (3) |
| VERIFIED | Delivered (3) — 验证通过但链上仍为 Delivered |
| DISPUTED | Disputed (5) |
| RELEASED | Confirmed (4) — 链上 = Confirmed = 释放给卖家 |
| RESOLVED_RELEASE | Confirmed (4) — 仲裁释放，链上等价 |
| RESOLVED_REFUND | Refunded (6) — 仲裁退款 |
| EXPIRED | Expired (7) — 超时自动释放 |
| REFUNDED_TIMEOUT | Refunded (6) — 超时退款 |

三个 off-chain-only 状态 (VERIFIED, RESOLVED_RELEASE, REFUNDED_TIMEOUT) 在链上坍缩为最近的等价状态。这意味着：

- 验证评分和 split 仲裁发生在 off-chain
- 最终资金移动在链上是二元的（释放或退款）
- 链上不支持 split/partial 分割

### 4.4 正向路径 API

Escrow 正向路径由 7 个端点组成完整生命周期：

| 端点 | 转换 | 鉴权 |
|------|------|------|
| `POST /escrow/create` | → CREATED | requireAdmin |
| `POST /escrow/:id/fund/prepare` | 返回 MetaMask 参数 | injectToken |
| `POST /escrow/:id/fund/confirm` | CREATED → FUNDED | injectToken |
| `POST /escrow/:id/seller-accept` | FUNDED → EXECUTING | injectToken (wallet 匹配) |
| `POST /escrow/:id/deliver` | EXECUTING → DELIVERED | injectToken (wallet 匹配) |
| `POST /escrow/:id/verify` | 三分支判定 | injectToken |
| `POST /escrow/:id/release` | VERIFIED → RELEASED | injectToken |

---

## 5. Voucher 按量计费

### 5.1 概念

Voucher 是预付费按量使用 Agent 服务的凭证。买家预付一笔押金，按消费单位递增扣费，直到耗尽或取消。

Voucher 与 Escrow 形成双层金融结构：Escrow 锁定全部预付金额作为押金安全，Voucher 在其上追踪增量消费。

### 5.2 状态机

7 个状态，4 个终态：

| 状态 | 含义 | 终态? |
|------|------|-------|
| ISSUED | 预付费但未激活 | 否 |
| ACTIVE | 正在消费单位 | 否 |
| EXHAUSTED | 全部单位耗尽 | 终态 |
| DISPUTED | 争议 | 否 |
| RESOLVED_REFUND | 仲裁退款 | 终态 |
| RESOLVED_RELEASE | 仲裁释放 | 终态 |
| CANCELLED | 取消 | 终态 |

转换规则：

```
ISSUED ── activate ──→ ACTIVE ── use ──→ ACTIVE (units_used++)
                              │                │ exhaust (全部耗尽)
                              │                ↓
                              │          EXHAUSTED (自动释放)
                              │ dispute / cancel
                              ↓
                        DISPUTED ── arbitrate ──→ RESOLVED_REFUND / RESOLVED_RELEASE
```

关键设计：`use` 是自环转换 (ACTIVE → ACTIVE)，代表增量消费而不改变状态。耗尽是独立的显式动作 `exhaust`。

### 5.3 累计消费链验证

每条 `UsageRecord` 包含：
- `units_consumed`: 本次增量
- `cumulative_used`: 累计总消费（单调递增）
- `previous_cumulative`: 前一条记录的累计值（链指针）
- `timestamp`, `signature`

验证规则：

1. **单调性**: `cumulative_used` 必须严格递增（不能回退或停滞）
2. **链完整性**: 每条记录的 `previous_cumulative` 必须等于前一条的 `cumulative_used`，断裂 = 篡改证据
3. **超额检测**: `cumulative_used > total_units` → 进入争议

这个设计形成类似 hash chain 的结构，通过 `previous_cumulative` 指针实现篡改可检测，不需要在累计值上做加密哈希（`signature` 字段提供额外的签名保障）。

### 5.4 数据模型

```python
Voucher(
    voucher_id,         # 唯一 ID
    issuer_wallet,      # 买家 (预付费方)
    agent_id,           # 卖家 Agent
    capability_task_type, # 任务类型 (如 "data_delivery")
    unit_price,         # 单价 (Decimal)
    unit_type,          # 单位标签 (如 "api_call", "token_analysis")
    total_units,        # 预购总单位数
    units_used,         # 已消费单位数
    total_deposit,      # = total_units × unit_price
    escrow_id,          # 关联的 Escrow 订单 (押金安全)
    channel_id,         # 结算通道
    chain,              # 链
)
```

派生属性: `units_remaining = total_units - units_used`, `remaining_deposit = unit_price × units_remaining`

---

## 6. Session Key 授权

### 6.1 问题

Agent 需要执行链上操作（支付、托管、交付），但直接使用主钱包私钥意味着：
- 主私钥暴露给 Agent 进程
- Agent 没有操作范围限制
- 主钱包无法实时监控 Agent 行为

### 6.2 设计

Session Key 是从主钱包派生的受限密钥，主钱包通过签名授权 Agent 使用派生密钥，无需暴露主私钥。

**生命周期**:

1. **创建**: 从 `SHA256(main_private_key : agent_id : main_wallet)` 派生 ECDSA 密钥对。主钱包签署授权消息，生成 `authorization_signature`。
2. **使用**: Agent 用派生密钥签名支付请求，每次使用后 `total_used` 递增。
3. **撤销**: 主钱包签名撤销消息，nonce++ 并设 `revoked=True`。
4. **提额**: 主钱包签名提额消息，`total_quota += additional_quota`。

### 6.3 权限模型 (五维度受限授权)

| 参数 | 说明 | 约束类型 |
|------|------|----------|
| `available_chains` | 可操作的链列表 | 白名单 |
| `per_tx_limit` | 单笔交易最大金额 | 上限 |
| `total_quota` | 总消费额度 | 上限 |
| `callable_actions` | 可调用动作 (pay, escrow, deliver) | 白名单 |
| `expires_at` | 过期时间戳 | 时间约束 |
| `nonce` | 撤销计数器 | 防重放 |

**权限检查 (`can_spend`)**: 四个条件必须全部通过：
1. `chain ∈ available_chains`
2. `action ∈ callable_actions`
3. `amount ≤ per_tx_limit`
4. `total_used + amount ≤ total_quota`

### 6.4 授权消息格式

结构化的人类可读消息，用于主钱包签名授权：

```
CryptoMinds session key authorization
Agent: {agent_id}
Chains: {comma-separated chains}
PerTxLimit: {per_tx_limit}
TotalQuota: {total_quota}
Actions: {comma-separated actions}
Nonce: {nonce}
Expires: {expires_at}
SessionAddress: {session_address}
```

这种格式使得授权内容对人类和程序都可审计。未来如果需要 EIP-712 结构化签名，可以从这个格式直接映射。

### 6.5 降级模式

当 `eth_account` 不可用时，降级为 HMAC-SHA256 模式：
- 密钥派生用 HMAC 代替 ECDSA
- 签名用 HMAC 代替 ECDSA
- 此模式下无法恢复签名者地址，依赖 nonce 验证代替

---

## 7. 验证层

### 7.1 验证门抽象

每个验证门 (`VerificationGate`) 定义一类任务的验证逻辑：

- `validate_input(TaskInput)` — 输入格式验证
- `validate_output(TaskOutput)` — 输出格式验证
- `verify(TaskInput, TaskOutput)` → `VerificationResult` — 核心判定

`VerificationResult` 包含: `success`, `score` (0-1), `gate_id`, `evidence`, `error`。

### 7.2 三分支判定

验证不是 pass/fail 二元判定，而是三分支：

| 分支 | 条件 | 结果 | Escrow 转换 |
|------|------|------|-------------|
| verify_pass | `score ≥ threshold` | 交付合格 | DELIVERED → VERIFIED |
| verify_low_score | `score < threshold` 但 > 0 | 部分合格 | DELIVERED → DISPUTED |
| verify_fail | `success = False` 或 `score = 0` | 交付失败 | DELIVERED → DISPUTED |

三分支设计的原因：
- **binary fail 太粗暴**: 数据交付可能只是格式稍有偏差，不是完全失败
- **争议是正确的中间态**: 低分交付进入争议，让仲裁引擎根据双方信誉分决定
- **信誉分作为仲裁权重**: 高信誉卖家的低分交付可能只是运气差，低信誉卖家则是系统性问题

### 7.3 已实现验证门

| 验证门 | gate_id | 任务类型 | 验证方式 |
|--------|---------|----------|----------|
| TokenDeliveryGate | token_delivery | 代币交付 | 链上 Transfer 事件 + 余额验证 |
| DataDeliveryGate | data_delivery | 数据交付 | SHA256 哈希 + 格式验证 + 大小检查 |
| ComputeResultGate | compute_result | 计算结果 | 结果哈希 + 约束检查 |
| SignalContentGate | signal_content | 信号+内容 | 时间戳 + 模式匹配 |

**TokenDeliveryGate 详细验证逻辑**:

1. 获取交易 receipt，检查 status == 1
2. 在 receipt logs 中搜索 ERC20 Transfer 事件
3. 验证 `topic[2]` (recipient) == buyer_wallet
4. 解析 `data` 获取转账金额
5. 验证 `amount ≥ expected_min × (1 - slippage)`
6. 查询买家钱包代币余额二次确认

**DataDeliveryGate 详细验证逻辑**:

1. 检查 `data` 或 `file_hash` 存在
2. 计算 `SHA256(data)` 与 `expected_hash` 比对
3. 检查数据大小在 `[min_size, max_size]` 范围内
4. 如果指定 `expected_format` (json/csv/text/base64)，做格式校验
5. 评分：默认 1.0，可接受 `quality_score` 参数

---

## 8. Agent 层

### 8.1 能力描述 (CapabilitySpec)

每个 Agent 声明一组能力，每个能力是一个 `CapabilitySpec`：

```python
CapabilitySpec(
    task_type,           # 任务类型 (如 "token_delivery")
    verification_gate,   # 对应的验证门 ID
    pricing_model,       # 计价模式: fixed / percentage / dynamic / metered
    base_price,          # 基础价格 (fixed/dynamic)
    percentage_rate,     # 百分比费率 (percentage)
    unit_price,          # 单价 (metered)
    unit_type,           # 单位标签 (metered, 如 "api_call")
    supported_chains,    # 支持的链列表
    supported_channels,  # 支持的结算通道列表
    params,              # 链特定配置 (如 max_amounts, exchange_lists)
    available,           # 是否可用
    max_concurrent,      # 最大并发任务数
)
```

四种计价模式：

| 模式 | 计算 | 场景 |
|------|------|------|
| fixed | `base_price` | 固定价格服务 |
| percentage | `amount × percentage_rate` | 代币买入（费率） |
| dynamic | `base_price` (fallback) | 未来扩展 |
| metered | `unit_price × units` | API 调用、计算推理 |

### 8.2 Agent 能力 (AgentCapability)

完整的 Agent 描述符：

```python
AgentCapability(
    agent_id,            # Agent ID
    name,                # 名称
    wallet,              # 主钱包地址
    endpoint,            # 服务端点
    capabilities,        # CapabilitySpec 列表
    reputation,          # ReputationInfo
    staked,              # 已质押金额
    active_tasks_value,  # 当前活跃任务价值
    online,              # 是否在线
)
```

**质押容量**: `available_quota = staked - active_tasks_value`

**接单条件 (`can_accept`)**: 四个条件全部满足：
1. Agent 在线 (`online = True`)
2. 可用容量足够 (`available_quota ≥ amount`)
3. 有匹配 task_type 和 chain 的 CapabilitySpec
4. 价格条件满足（fixed: `amount ≥ base_price`; percentage: 无限制）

### 8.3 发现与匹配

`AgentRegistry` 维护所有注册 Agent 的能力索引。`find_best_match(task_type, chain, amount)` 搜索流程：

1. 筛选: task_type 匹配 + chain 匹配 + online + can_accept
2. 排序: 信誉分优先（`reputation.score`），价格次之
3. 返回: 最佳匹配 Agent

### 8.4 Agent 守护进程

`agent_daemon.py` 实现 Agent 运行时：

- **任务队列**: 线程安全队列，支持并发执行
- **执行器**: 可注册自定义执行器函数
- **状态机**: idle → working → idle 循环
- **并发控制**: `max_concurrent` 限制并发任务数

### 8.5 自主下单流程

`agent_buy` 实现买家 Agent 自主购买：

1. `find_best_match(task_type, chain, amount)` → 选择卖家 Agent
2. `create_task(buyer_wallet, seller_wallet, ...)` → 创建任务
3. 等待卖家交付
4. `verify_task()` → 三分支判定
5. 根据判定结果触发 Escrow 状态推进

---

## 9. 信誉层

### 9.1 信誉分计算

信誉分是 0-5 的连续值，基于五个维度：

```
score = success_score + quality_score + volume_score + response_score + recent_bonus - dispute_penalty

success_score    = success_rate × 3                    [0, 3]
quality_score    = avg_verification_gate_score         [0, 1]
volume_score     = min(0.5, log10(total_volume+1)×0.15) [0, 0.5]
response_score   = response_rating × 0.5               [0, 0.5]
recent_bonus     = 0.3 if last_24h_success ≥ 0.98
                   0.2 if last_24h_success ≥ 0.95
                   0.1 if last_24h_success ≥ 0.90
                   0   otherwise                       [0, 0.3]
dispute_penalty  = dispute_rate × 1.0                  [0, 1]

Final: clamp(score, 0, 5)
```

**维度权重解析**:

| 维度 | 权重范围 | 理由 |
|------|----------|------|
| 成功率 | 0-3 (60%) | 最核心指标——Agent 能不能按时交付 |
| 质量 | 0-1 (20%) | 交付的东西好不好（验证门评分） |
| 交易量 | 0-0.5 (10%) | 经验积累——做得多 = 更可靠 |
| 响应时间 | 0-0.5 (10%) | 速度——Agent 经济需要秒级响应 |
| 近期加成 | 0-0.3 | 鼓励持续活跃，惩罚"躺平赚信誉" |
| 争议惩罚 | 0-1 | 直接扣分——争议是负面信号 |

**响应时间评级**:

| 阈值 | 评级 |
|------|------|
| < 1s | 1.0 (excellent) |
| < 5s | 0.8 (good) |
| < 30s | 0.5 (acceptable) |
| ≥ 30s | 0.2 (slow) |
| 无数据 | 0.5 (neutral) |

### 9.2 信誉等级

| 分数范围 | 等级 | 含义 |
|----------|------|------|
| ≥ 4.5 | S | 顶级 Agent，高成功率+高质量+活跃 |
| ≥ 4.0 | A | 可信赖，偶有小问题 |
| ≥ 3.5 | B | 一般水平，争议率偏高 |
| ≥ 3.0 | C | 有风险，争议频繁 |
| < 3.0 | D | 不可信赖，可能被禁用 |

### 9.3 信誉分的作用

信誉分在协议中扮演三重角色：

1. **Agent 发现排序**: 市场搜索按 `reputation.score` 排序，高信誉优先展示
2. **仲裁权重**: 争议自动解决时，双方信誉分决定仲裁倾向
3. **信用货币发行门槛**: 信誉分 ≥ 4.0 才有资格发行信用货币

### 9.4 争议仲裁引擎

当 Escrow 进入 DISPUTED 状态，仲裁引擎 (`ArbitrationEngine`) 决定资金归属。

**仲裁决策**: 三种结果：
- `buyer_win`: 退款给买家
- `seller_win`: 释放给卖家
- `split`: 按验证分比例分割（seller 得 `score × amount`, buyer 得 `(1-score) × amount`）

注意：split 在链上是二元的——当前映射为 `arbitrate_seller_win`。真正的分割需要合约升级支持 partial release。

**仲裁权重计算**:

```
buyer_weight   = (success_records_in_last_10 / 10) × 5.0
seller_weight  = seller_agent.reputation.score

normalized    = (buyer_weight / total, seller_weight / total)
                where total = buyer_weight + seller_weight
                fallback   = (0.5, 0.5) if both zero
```

**超时自动解决**: 争议窗口过期后，`arbitration_weight_seller > arbitration_weight_buyer` → seller_win，反之 buyer_win。双方权重相等时，默认 seller_win（乐观路径——倾向于信任已交付的卖家）。

### 9.5 Seller Slashing 规则

对卖家 Agent 的惩罚机制：

| 近期 buyer_win 争议次数 | 惩罚 |
|------------------------|------|
| 1 次 | 信誉分 -0.3 |
| 3 次 (7天内) | 信誉分 -1.0 + stake slash 50% |
| 5+ 次 | 信誉分设为 0, Agent 设为 offline |

Slashing 设计的目的：

- **递进惩罚**: 不是一争议就重罚，而是累计效应
- **stake slash**: 3 次争议不仅扣信誉，还割质押金的一半，补偿买家损失
- **硬性禁用**: 5 次以上争议直接禁用，防止系统性不良 Agent 继续伤害

---

## 10. 信用货币系统

### 10.1 概念

信用货币 (`CreditCurrency`) 是高信誉 Agent 发行的 IOU，代表该 Agent 的履约承诺。发行者承诺：持有者可以用此货币支付我的服务，我保证按面值接受。

这是 Agent 经济中的"内部信用系统"——不需要外部稳定币，Agent 自身的信誉就是货币的背书。

### 10.2 发行规则

- **发行门槛**: 信誉分 ≥ 4.0 (等级 A 或 S)
- **一对一**: 每个发行者钱包只能发行一种信用货币
- **质押比率**: `min_stake_ratio = 0.5`（发行量不超过质押的 2 倍）
- **初始发行**: `max_supply` 全部 mint 给发行者

```python
CreditCurrency(
    currency_id,         # 唯一 ID
    issuer_agent_id,     # 发行 Agent
    issuer_wallet,       # 发行钱包
    name,                # 名称
    symbol,              # 符号
    total_supply,        # 当前供应量
    max_supply,          # 最大供应量
    backed_by,           # 背书描述 (如 "BNB staking collateral")
    min_reputation_score,# 最低信誉分门槛 (default 4.0)
    min_stake_ratio,     # 最低质押比率 (default 0.5)
    accepted_by,         # 接受此货币的 Agent 列表
)
```

### 10.3 信任分计算

```python
trust_score = acceptance_score × 0.5 + (min_reputation_score / 5.0) × 0.5

where:
    acceptance_score = min(1.0, len(accepted_by) / 10)
```

两个维度：
- **接受度**: 有多少 Agent 接受此货币作为支付（共识信任）
- **发行者信誉门槛**: 门槛越高 = 发行者筛选越严格 = 货币更安全

### 10.4 支付规则

信用货币支付要求：
- 收款 Agent 必须已明确接受该货币 (`to_agent_id ∈ accepted_by`)
- 发送者余额足够
- 不满足接受条件的支付会被拒绝

---

## 11. 智能合约规范

### 11.1 ServiceEscrow.sol (BSC)

**合约地址**: 由环境变量 `ESCROW_CONTRACT_ADDRESS` 或 `escrow_deployment.json` 配置

**OrderStatus 枚举**:

| 值 | 名称 | 含义 |
|----|------|------|
| 0 | None | 订单不存在 |
| 1 | Pending | BNB 已锁定，等待卖家 |
| 2 | Delivering | 卖家已接单，执行中 |
| 3 | Delivered | 卖家提交交付 |
| 4 | Confirmed | 买家确认；BNB 释放给卖家 |
| 5 | Disputed | 买家争议；等待仲裁 |
| 6 | Refunded | 退款给买家 |
| 7 | Expired | 买家确认超时；自动释放给卖家 |

**Order 结构体**:
- buyer, seller (address)
- serviceId (string)
- amount (uint256, wei)
- createdAt, deliveredAt, buyerTimeoutAt, sellerTimeoutAt (uint256)
- status (OrderStatus)
- deliverResult (string)

**合约方法**:

| 方法 | 调用者 | 状态变化 | 说明 |
|------|--------|----------|------|
| `createOrder` | buyer | → Pending | `msg.value > 0`, order_id = keccak256(buyer, seller, serviceId, timestamp, count) |
| `deliver` | seller | Pending → Delivered | 必须在 `sellerTimeoutAt` 前 |
| `confirm` | buyer | Delivered → Confirmed | BNB `call{value}` 释放给卖家 |
| `dispute` | buyer | Delivered → Disputed | 买家发起争议 |
| `claimBuyerTimeout` | anyone | Delivered → Expired | 买家超时后，BNB 释放给卖家 |
| `claimSellerTimeout` | anyone | Pending/Delivering → Refunded | 卖家超时，退款给买家 |
| `arbitrateRefund` | owner | Disputed → Refunded | 管理员仲裁退款 |
| `arbitrateRelease` | owner | Disputed → Confirmed | 管理员仲裁释放 |

**设计要点**:

1. **纯 BNB**: 不支持 ERC-20，简化合约逻辑
2. **公共看门狗模式**: `claimBuyerTimeout/claimSellerTimeout` 任何人可调用，鼓励第三方监控超时
3. **超时默认值**: 买家确认 24 小时, 卖家交付 30 分钟
4. **交付后重置**: buyer timeout 从交付时间重新计算
5. **二元仲裁**: 链上不支持分割，仲裁只有 refund/release 两种结果
6. **统计追踪**: 合约记录 totalEscrowed, totalReleased, totalRefunded, totalDisputed

### 11.2 链上/链下协作模式

```
                     链下 (off-chain)                   链上 (on-chain)
                     ────────────────                   ────────────────
验证评分           →  score 0-1, 三分支判定             →  不支持
分割仲裁           →  split: score × amount             →  不支持 (二元)
信誉加权           →  weight based arbitration          →  不支持
状态细节           →  11 states                         →  8 states
资金移动           →  不直接                             →  call{value} 释放/退款
```

链下负责判定逻辑，链上负责资金安全。两者通过状态映射和 `on_chain_order_id` 关联。

---

## 12. 威胁模型与安全分析

### 12.1 参与者角色

| 角色 | 能力 | 信任假设 |
|------|------|----------|
| 买家 Agent | 创建订单、锁定资金、发起争议 | 可能恶意争议 |
| 卖家 Agent | 接单、交付、请求释放 | 可能不交付、交付质量低 |
| 管理员 | 创建订单、仲裁争议、链上操作 | 信任——但最小权限 |
| 第三方看门狗 | 调用 timeout claim | 不信任——但行为受合约约束 |
| 协议服务 | 状态推进、验证评分 | 信任——但不接触资金 |

### 12.2 威胁分析

**T1: 卖家不交付 (seller no-delivery)**
- 威胁: 卖家接单后不交付
- 缓解: `seller_timeout` → REFUNDED_TIMEOUT，资金自动退回
- 残余风险: 资金锁定期间卖家占用买家流动性

**T2: 卖家交付质量低 (seller low-quality)**
- 威胁: 卖家提交低质量结果
- 缓解: 验证门评分 + 三分支 → 低分进入 DISPUTED → 仲裁
- 残余风险: 仲裁可能 seller_win（卖家信誉高）

**T3: 买家恶意争议 (buyer malicious dispute)**
- 威胁: 买家收到合格交付后恶意争议
- 缓解: 仲裁引擎比较双方信誉权重，高信誉卖家倾向 seller_win
- 残余风险: 新买家（无信誉记录）权重为 0，默认倾向 seller_win

**T4: 管理员滥用 (admin abuse)**
- 威胁: 管理员在仲裁中偏袒一方
- 缓解: 管理员只能从 DISPUTED 状态操作，且链上操作是 owner-only
- 残余风险: 单点信任——管理员是信任根
- 改进方向: 多签仲裁 / DAO 投票

**T5: 链上合约漏洞 (smart contract vulnerability)**
- 威胁: ServiceEscrow.sol 有 bug，导致资金损失
- 缓解: 合约逻辑极简（只做锁定/释放/退款），状态转换受合约约束
- 残余风险: 重入攻击、整数溢出（Solidity 0.8+ 内置溢出检查）

**T6: 私钥泄露 (private key exposure)**
- 威胁: Agent 主私钥泄露，攻击者控制所有资金
- 缓解: Session Key 机制——主私钥不传给 Agent 进程，仅用派生密钥
- 残余风险: Session Key 创建时仍需主私钥（Demo 模式下用 placeholder）

**T7: 验证门欺骗 (verification gate spoofing)**
- 威胁: 卖家伪造交付证据
- 缓解: 验证门要求链上证据（tx_hash + Transfer event），数据类要求 SHA256 哈希
- 残余风险: Mock 通道无链上验证（仅测试用）

**T8: 信誉分操纵 (reputation manipulation)**
- 威胁: Agent 通过大量小额自成交提升信誉分
- 缓解: `volume_score` 使用 `log10` 缩放，小额交易贡献极小
- 残余风险: 仍可能通过 `recent_bonus` 操纵（需要 last_24h_success ≥ 0.98）

**T9: SSRF 攻击 (Server-Side Request Forgery)**
- 威胁: Agent 注册恶意端点，诱导服务器请求内网
- 缓解: 安全扫描 10 种检测模式 + 域名白名单 + IP 范围过滤
- 残余风险: DNS rebinding 可绕过 IP 检查

**T10: 时序攻击 (timing attack on admin secret)**
- 威胁: 通过响应时间差异猜测 admin secret
- 缓解: Express 使用 `crypto.timingSafeEqual` 做常量时间比较
- 已知问题: Python 端的 admin secret 比较仍用 `!=`（非 timing-safe）

### 12.3 安全假设

| 假设 | 说明 | 失效后果 |
|------|------|----------|
| H1: 管理员诚实 | 管理员不偏袒仲裁 | 仲裁公平性丧失 |
| H2: 链上合约正确 | ServiceEscrow.sol 无漏洞 | 资金可能被盗 |
| H3: SQLite 可用 | 数据库不崩溃不丢数据 | 状态记录丢失 |
| H4: RPC 可用 | BSC/ETH/SOL RPC 端点正常 | 无法验证链上交易 |
| H5: Agent 不自交 | Agent 不会大量自成交刷信誉 | 信誉分可能被操纵 |

### 12.4 已知安全缺陷 (生产上线前必须修复)

| 优先级 | 缺陷 | 影响 |
|--------|------|------|
| P0 | 无 TLS/SSL | HTTP 传输，凭据可被窃听 |
| P0 | Python admin 比较非 timing-safe | 时序攻击可猜测 admin secret |
| P0 | wallets.json 含真实私钥 | 本地文件泄露 = 资金损失 |
| P0 | Docker CMD 后台化 Python | 进程管理不可靠 |
| P1 | CORS 未限制 | 跨域攻击 |
| P1 | Flask 开发服务器 | 不适合生产 |
| P1 | SQLite 单写并发 | 高并发写入瓶颈 |

---

## 13. 经济机制设计

### 13.1 市场机制

CryptoMinds 市场是**双边 Agent 市场**：

- **供给侧**: 卖家 Agent 注册能力声明 + 质押 BNB
- **需求侧**: 买家 Agent 搜索匹配 + 自主下单
- **匹配算法**: task_type → chain → reputation → price

市场排序公式:

```
market_score = effective_rate × 0.4 + reputation × 0.3 + volume × 0.3
```

Smart Router 在支付路径选择中：

```
path_score = cost_score × 0.4 + success_rate × 0.6
```

其中 `success_rate` 是 reputation-adjusted 的。

### 13.2 质押-容量约束

卖家必须质押资金才能接单。这是**保证金机制**：

- `available_quota = staked - active_tasks_value`
- 质押越多 → 可接任务越多 → 收入潜力越大
- 质押金在争议中可能被 slashing（3次争议 slash 50%，5次争议全部）

**机制目的**:
1. **准入门槛**: 防止零成本 Agent 进入市场伤害买家
2. **行为约束**: 质押金是惩罚的"弹药"
3. **容量信号**: 质押量 = Agent 对自身能力的信心

### 13.3 Escrow 的博弈分析

Escrow 托管改变了买卖双方的博弈结构：

**无 Escrow (直接支付)**:
- 买家先付 → 卖家可以不交付 (buyer's dilemma)
- 卖家先交付 → 买家可以不付 (seller's dilemma)

**有 Escrow**:
- 买家锁定资金 → 卖家知道钱已到位，有动力交付
- 资金在合约中 → 买家知道卖家不交付可以退款
- 争议 → 仲裁引擎根据信誉决定归属

这解决了 Agent 经济中的**信任悖论**: 双方都不信任对方，但都信任合约和仲裁规则。

### 13.4 信誉分的经济学

信誉分是**信息信号**，解决 Agent 市场的信息不对称：

- **高质量 Agent** 通过高信誉分获得更多订单和更高权重
- **低质量 Agent** 信誉分下降，订单减少，最终被禁用
- **新 Agent** 从零开始，需要小额交易积累信誉（volume_score 的 log10 缩放鼓励渐进积累）

信誉分的**时间衰减**通过 `recent_bonus` 实现——只有持续活跃才能维持 S/A 等级。"躺平赚信誉"不可行。

### 13.5 信用货币的流通机制

信用货币是**信誉的衍生品**:

- 发行者信誉 ≥ 4.0 → 有资格发行
- `accepted_by` 列表 = 信任共识
- `min_stake_ratio = 0.5` = 2:1 杠杆上限

**信任分** 衡量信用货币的风险：

- 高接受度 + 高信誉门槛 → 高信任分 → 适合作为支付媒介
- 低接受度 + 低信誉门槛 → 低信任分 → 不适合广泛流通

这为 Agent 经济创造了**内部货币体系**，不依赖外部稳定币。但当前信用货币尚未广泛流通——需要先建立交易基础。

---

## 14. 架构决策记录

### ADR-1: SQLite 作为数据层

**决策**: 使用 SQLite 而非 PostgreSQL/Redis

**理由**:
- Agent 经济初期交易量有限（SQLite WAL mode 支持并发读）
- 单文件部署，无额外运维
- Python 内置支持，无外部依赖
- 未来可迁移到 PostgreSQL（store 类抽象隔离了数据层）

**后果**:
- ✅ 部署简单，测试容易（tmp_path fixture）
- ❌ 单写并发限制（写入串行化）
- ❌ 无内置复制/备份

### ADR-2: 双端口架构 (Express + Flask)

**决策**: Express 3457 做统一入口代理，Flask 3458 做协议核心

**理由**:
- Node.js 有更好的 HTTP 代理和 WebSocket 支持
- Python 有更好的加密库（eth_account, web3.py）
- 分层认证让 Express 只做 token 注入，不做业务鉴权

**后果**:
- ✅ 前端只需连一个端口
- ✅ 认证逻辑清晰分层
- ❌ 两个进程运维复杂度
- ❌ Python API 内部 token 需要环境变量配置

### ADR-3: 验证门三分支

**决策**: 验证结果分 pass/low_score/fail 三条路径

**理由**:
- binary fail 太粗暴——"数据格式略有偏差" 和 "完全没交付" 应该不同处理
- 低分进入争议让仲裁引擎根据双方信誉决定
- 高信誉卖家的低分交付可能是偶发问题，不应直接退款

**后果**:
- ✅ 争议处理更公平
- ❌ 增加了 DISPUTED 状态的仲裁负担
- ❌ 需要仲裁引擎设计（比直接 pass/fail 复杂）

### ADR-4: Session Key ECDSA 派生

**决策**: 从主私钥派生 ECDSA 密钥，而非独立生成

**理由**:
- 派生密钥可追溯——知道 session address 就能验证它属于哪个主钱包
- 无需额外存储派生映射（SHA256 是确定性函数）
- 主钱包签名授权消息作为权限声明

**后果**:
- ✅ 无需额外密钥管理
- ✅ 授权可审计
- ❌ 知道主私钥就能算出所有 session key（不是独立密钥）
- ❌ HMAC 降级模式下安全性降低

### ADR-5: 链上二元仲裁

**决策**: ServiceEscrow.sol 只支持 refund/release 两种仲裁结果，不支持 split

**理由**:
- 合约越简单越安全
- Split 需要部分转账逻辑，增加合约复杂度和 gas 成本
- Split 在链下计算，链上只执行最终结果

**后果**:
- ✅ 合约逻辑极简，安全审计容易
- ❌ split 仲裁在链上映射为 seller_win，买家未获得部分退款
- 改进方向: 合约升级支持 partial release

### ADR-6: 信誉分 0-5 量表

**决策**: 信誉分使用 0-5 量表而非 0-100 或 0-1

**理由**:
- 5 分量表与等级映射直观 (S/A/B/C/D)
- 0-5 范围允许各维度有不同权重贡献而不溢出
- `success_rate × 3` 最大贡献 3 分，给质量/量/速度留空间

**后果**:
- ✅ 直观易理解
- ✅ 维度权重自然分配
- ❌ 精度有限（0.1 分差异可能影响等级）

### ADR-7: Escrow 11 状态 vs 链上 8 状态

**决策**: Off-chain 维持 11 个状态，映射到链上 8 个

**理由**:
- 验证评分 (VERIFIED) 和争议结果细分 (RESOLVED_RELEASE vs RESOLVED_REFUND) 在链下有意义
- 链上合约不需要这些细分——只关心资金是否移动

**后果**:
- ✅ 链下状态丰富，支持细粒度业务逻辑
- ✅ 链上合约极简
- ❌ 映射复杂，需要维护两套状态转换规则

### ADR-8: Voucher 与 Escrow 双层结构

**决策**: Voucher 通过 `escrow_id` 关联 Escrow 订单

**理由**:
- Voucher 的押金安全由 Escrow 提供（锁定全额预付款）
- Voucher 只追踪消费进度，不负责资金安全
- 资金争议走 Escrow 仲裁，消费争议走 Voucher 仲裁

**后果**:
- ✅ 责责分离——消费逻辑和资金安全分开
- ✅ Voucher 争议可以引用 Escrow 的仲裁结果
- ❌ 双层管理复杂——需要维护两个状态机的联动

### ADR-9: 公共看门狗模式

**决策**: `claimBuyerTimeout` 和 `claimSellerTimeout` 任何人可调用

**理由**:
- 买家/卖家可能故意不触发 timeout claim（一方获利时）
- 第三方无利益冲突，可以客观执行
- 鼓励生态中的监控 Agent 专门做看门狗

**后果**:
- ✅ 无人"睡着"——timeout 总会被触发
- ❌ 需要有人/Agent 愿意做看门狗（目前依赖管理员监控）
- 改进方向: 协议服务自动扫描超时订单

---

## 15. 未来方向

### 15.1 近期 (BSC 测试网)

| 项 | 优先级 | 说明 |
|----|--------|------|
| TLS/SSL 终止 | P0 | HTTPS 加密传输 |
| chainId/RPC 校验 | P0 | 测试网交易必须使用 `BSC_CHAIN_ID=97` |
| 写接口认证 | P0 | internal token、管理员密钥或钱包签名 |
| 押金链上验证 | P0 | deposit tx + receipt success |
| timing-safe admin 比较 | P0 | 管理员密钥比较 |
| 私钥保护 | P0 | 加密存储或 HSM |
| Docker 进程管理 | P0 | 前台运行 + 健康检查 |
| 监控告警 | P1 | Prometheus + Grafana |
| 数据库备份 | P1 | PostgreSQL volume 备份 |

### 15.2 中期 (SACRED 信用分)

| 项 | 说明 |
|----|------|
| 五维信用画像 | Stability / Activity / Creditworthiness / Reliability / Ecosystem |
| 冷启动保护 | 新 Agent 初始分、快速通道、退出冷启动阈值 |
| 授权查询 | Agent 授权第三方查看信用档案 |
| 排行榜与画像页 | 历史趋势、同行对比、风险提示 |
| 小流量接入 | 先影响排序，再影响额度、押金折扣和仲裁权重 |

### 15.3 中远期 (生态扩展)

| 项 | 说明 |
|----|------|
| 更多链支持 | Polygon, Arbitrum, Base |
| 合约升级 | partial release, ERC-20 托管 |
| 多签仲裁 | DAO 投票替代单管理员 |
| SPL Token 转账 | Solana 代币交互 |
| 看门狗 Agent | 自动监控超时订单 |
| Web UI 完善 | Escrow/Voucher 全流程可视化 |

### 15.4 远期 (Agent 经济体)

| 项 | 说明 |
|----|------|
| Agent 衍生服务 | 保险 Agent、预测市场 Agent |
| 信用货币流通 | 建立交易基础后启动 |
| 跨协议互操作 | 与其他 Agent 协议的桥接 |
| Agent DAO | 由 Agent 组成的治理组织 |

---

## 附录 A: 测试覆盖

| 类型 | 数量 | 覆盖 |
|------|------|------|
| pytest 单元测试 | 777 passed, 1 skipped | 73.11% 代码覆盖, 70% 门槛 |
| E2E 测试 | 覆盖协议正向路径、争议与安全回归 | 随 pytest / node:test 运行 |
| node:test | 10 | SQLite + API + 端口 |

## 附录 B: 数据层 Schema

**escrow_orders 表**: 20 列, 索引 on (state, seller_wallet, buyer_wallet, on_chain_order_id)

**session_keys 表**: 13 列, 索引 on (agent_id, main_wallet, session_address)

**performance_records 表**: 8 列, 細引 on (agent_id)

**credit 表**: currency_id + balances

**vouchers 表**: 24 列, 細引 on (agent_id, issuer_wallet, state)

## 附录 C: 环境变量

| 变量 | 说明 | 默认值 |
|------|------|---------|
| BSC_RPC | BSC RPC 端点 | 测试网建议 `https://bsc-testnet-dataseed.bnbchain.org` |
| BSC_CHAIN_ID | BSC chainId | 测试网 97，主网 56 |
| ESCROW_CONTRACT_ADDRESS | 合约部署地址 | — |
| DATABASE_URL | PostgreSQL 连接串 | Compose 默认指向 postgres |
| CRYPTOMINDS_DB_PATH | SQLite 数据库路径 | web/cryptominds.db |
| CRYPTOMINDS_INTERNAL_TOKEN | Python API 认证 token | — |
| ADMIN_SECRET | 管理员密钥 | — |
| DEMO_MODE | Demo 模式 (跳过链上验证) | false |
| SETTLEMENT_TEST_MODE | 结算测试模式 | false |

---

**License**: MIT

**联系方式**: GitHub Issues

**版本历史**: v2.5 — BSC Testnet hardening + SACRED credit-score roadmap
