# CryptoMinds API 文档

## 基础信息

- **统一入口**: `http://localhost:3457` (Node.js)
- **协议层**: `http://localhost:3458` (Python，内部微服务)
- **链**: BNB Chain (BSC), ETH, Solana, Mock
- **测试网合约**: 以 `ESCROW_CONTRACT_ADDRESS` 或 `escrow_deployment.json` 为准
- **测试网配置**: BSC Testnet 使用 `BSC_CHAIN_ID=97`

---

## 架构说明

```
客户端 → Node.js/Express Gateway (3457) → Python (3458)
              ↓
      PostgreSQL / SQLite
```

- Node.js 处理市场、订单、通知等业务逻辑
- Python 处理协议层（验证门、结算通道、Agent 注册）
- `/api/v1/protocol/*` 路由自动代理到 Python
- 旧 `/api/*` 会 301 到 `/api/v1/*`
- 非 Demo 模式下，市场写接口需要 internal token、管理员密钥或钱包签名

---

## 认证约定

### Internal Token

服务端内部调用使用：

```http
X-CryptoMinds-Internal-Token: <CRYPTOMINDS_INTERNAL_TOKEN>
```

### Admin Secret

管理员/仲裁接口使用：

```http
X-Admin-Secret: <ADMIN_SECRET>
```

### 钱包签名

市场直挂写接口支持钱包签名。请求失败时会返回 `expectedMessage`，客户端让对应钱包签名后把 `message` 和 `signature` 放入请求体重试。

## 市场 API

### 获取卖家列表
```
GET /api/v1/sellers
```
返回所有已激活的卖家服务。

### 获取市场信息
```
GET /api/v1/market
```
返回市场统计信息。

### 获取余额
```
GET /api/v1/balance?wallet=0x...
```

### 获取购买记录
```
GET /api/v1/purchases?wallet=0x...
```

### 创建订单
```
POST /api/v1/orders/create
```
```json
{
  "buyerWallet": "0x...",
  "sellerWallet": "0x...",
  "amount": 0.001,
  "serviceId": "seller-001",
  "input": "帮我买 1 BNB 的币",
  "message": "...",
  "signature": "0x..."
}
```

### 获取我的订单
```
GET /api/v1/purchases?wallet=0x...
```

### 确认收货
```
POST /api/v1/purchases/confirm/:orderId
```
- 如果订单走合约托管，前端需先调用合约 `confirm(escrowOrderId)`
- 后端更新评分和状态

---

## 卖家 API

### 入驻申请
```
POST /api/v1/sellers/register
```
```json
{
  "name": "Meme 狙击手",
  "description": "根据自己的策略执行 meme 买入并交付代币",
  "wallet": "0x...",
  "price": 0.001,
  "deposit": 0.1,
  "apiEndpoint": "https://...",
  "depositTx": "0x...",
  "message": "...",
  "signature": "0x..."
}
```

非 Demo 模式必须提供链上押金交易，且交易 receipt 成功。

### 提交交付结果
```
POST /api/v1/orders/:orderId/result
```
```json
{
  "output": "已自主选定 meme 并完成买入，代币已转入买家钱包",
  "sellerWallet": "0x...",
  "deliveryTxHash": "0x...",
  "message": "...",
  "signature": "0x..."
}
```
- 如果订单有 `escrowOrderId`，前端需先调用合约 `deliver(escrowOrderId, result)`
- 非 Demo 模式要求卖家钱包签名

### 获取卖家订单
```
GET /api/v1/orders?sellerWallet=0x...
```

---

## Escrow 合约 API

### 获取合约信息
```
GET /api/v1/escrow/info
```
```json
{
  "ok": true,
  "address": "0x...",
  "abi": [...]
}
```

### 获取合约统计
```
GET /api/v1/escrow/stats
```
```json
{
  "ok": true,
  "totalEscrowed": "0.001",
  "totalReleased": "0.0005",
  "totalRefunded": "0",
  "totalDisputed": "0",
  "orderCount": "5"
}
```

### 查询链上订单
```
GET /api/v1/escrow/order/:orderId
```

---

## 合约交互（前端 MetaMask）

### 创建订单（买家）
```javascript
escrowContract.methods.createOrder(
  sellerAddress,
  serviceId,
  buyerTimeoutSeconds,  // 86400 = 24小时
  sellerTimeoutSeconds  // 1800 = 30分钟
).send({ from: buyerWallet, value: web3.utils.toWei('0.001', 'ether') })
```

### 提交交付（卖家）
```javascript
escrowContract.methods.deliver(
  escrowOrderId,
  "交付结果描述"
).send({ from: sellerWallet })
```

### 确认收货（买家）
```javascript
escrowContract.methods.confirm(
  escrowOrderId
).send({ from: buyerWallet })
```

### 卖家超时退款（买家）
```javascript
escrowContract.methods.claimSellerTimeout(
  escrowOrderId
).send({ from: buyerWallet })
```

---

## Agent API (协议层)

### 注册 Agent
```
POST /api/v1/agents/register
```
```json
{
  "agent_id": "my-agent",
  "wallet": "0x...",
  "task_types": ["token_delivery", "data_delivery"],
  "supported_chains": ["bsc", "mock"],
  "capabilities": {...}
}
```

### 获取 Agent 列表
```
GET /api/v1/agents
```

### Agent 自主下单
```
POST /api/v1/agent-buy
```
```json
{
  "buyer_wallet": "0x...",
  "amount_bnb": 0.01,
  "task_type": "token_delivery",
  "params": {"keyword": "meme"}
}
```

---

## 协议 API (Python 微服务)

通过 Node.js 代理访问：`/api/v1/protocol/*`

### 协议信息
```
GET /api/v1/protocol/info
```

### 结算通道列表
```
GET /api/v1/protocol/channels
```

### 验证门列表
```
GET /api/v1/protocol/gates
```

### 创建任务
```
POST /api/v1/protocol/tasks/create
```
```json
{
  "task_type": "token_delivery",
  "buyer_wallet": "0x...",
  "seller_wallet": "0x...",
  "amount": 0.01,
  "chain": "bsc",
  "params": {...}
}
```

### 验证任务
```
POST /api/v1/protocol/tasks/verify
```
```json
{
  "task_id": "task-001",
  "output": {
    "tx_hash": "0x...",
    "token_address": "0x...",
    "token_amount": "1000000"
  }
}
```

---

## 通知 API

### 获取通知
```
GET /api/v1/notifications?wallet=0x...
```

### 标记已读
```
POST /api/v1/notifications/:id/read
```

---

## 管理员 API

需要 `X-Admin-Secret` header 或 `secret` query 参数。

### 获取待审核卖家
```
GET /api/v1/admin/pending-sellers?secret=xxx
```

### 审核通过
```
POST /api/v1/admin/approve-seller?secret=xxx
```
```json
{ "sellerId": "seller-001" }
```

---

## 状态流转

```
pending → delivered → confirmed
                    → disputed → refunded/confirmed
       → seller_timeout → refunded
```

| 状态 | 说明 |
|------|------|
| pending | 等待卖家交付 |
| delivered | 卖家已提交结果 |
| confirmed | 买家确认收货 |
| disputed | 买家发起争议 |
| refunded | 已退款 |
| seller_timeout | 卖家超时未交付 |

---

## Escrow 争议仲裁 API

通过 Node.js 代理访问：`/api/v1/protocol/escrow/*`

### 创建 Escrow 托管订单 (需 ADMIN_SECRET)
```
POST /api/v1/protocol/escrow/create
```
```json
{
  "task_id": "task-001",
  "buyer_wallet": "0x...",
  "seller_wallet": "0x...",
  "seller_agent_id": "agent-001",
  "amount": "0.5",
  "chain": "bsc",
  "verification_threshold": 0.7,
  "dispute_window_seconds": 172800
}
```
Headers: `X-Admin-Secret: <secret>`

### 获取 Escrow 状态
```
GET /api/v1/protocol/escrow/:escrowId
```

### 发起争议
```
POST /api/v1/protocol/escrow/:escrowId/dispute
```
```json
{
  "reason": "交付质量不达标",
  "initiator": "buyer"
}
```

### 管理员仲裁 (需 ADMIN_SECRET)
```
POST /api/v1/protocol/escrow/:escrowId/resolve
```
```json
{
  "decision": "buyer_win"
}
```
Headers: `X-Admin-Secret: <secret>`
decision 可选: `buyer_win`, `seller_win`, `split`

### 列出争议中的 Escrow
```
GET /api/v1/protocol/escrow/disputed
```

### Escrow 正向路径 (生命周期端点)

#### 准备链上锁定 (返回 MetaMask 参数)
```
POST /api/v1/protocol/escrow/:escrowId/fund/prepare
```
```json
{
  "buyer_timeout_seconds": 86400,
  "seller_timeout_seconds": 1800
}
```
Response 包含 `metamask_params`: contract_address, method, args, value, abi

#### 确认链上锁定 (CREATED → FUNDED)
```
POST /api/v1/protocol/escrow/:escrowId/fund/confirm
```
```json
{
  "on_chain_order_id": "0x...",
  "reason": "链上锁定确认"
}
```

#### 卖家接单 (FUNDED → EXECUTING)
```
POST /api/v1/protocol/escrow/:escrowId/seller-accept
```
```json
{
  "seller_wallet": "0x...",
  "reason": "接单"
}
```
需 seller_wallet 与订单匹配

#### 卖家交付 (EXECUTING → DELIVERED)
```
POST /api/v1/protocol/escrow/:escrowId/deliver
```
```json
{
  "seller_wallet": "0x...",
  "result": "交付内容",
  "evidence": {"key": "value"}
}
```

#### 验证门 (DELIVERED → VERIFIED 或 DISPUTED)
```
POST /api/v1/protocol/escrow/:escrowId/verify
```
```json
{
  "task_type": "token_delivery",
  "tx_hash": "0x...",
  "token_address": "0x..."
}
```
三分支逻辑:
- score >= threshold → VERIFIED
- score < threshold → DISPUTED (low_score)
- verification fail → DISPUTED (verify_fail)

#### 释放资金 (VERIFIED → RELEASED)
```
POST /api/v1/protocol/escrow/:escrowId/release
```
```json
{
  "actor": "buyer",
  "reason": "验证通过, 释放资金"
}
```
mock channel: 直接释放, 返回 tx_hash
BSC channel: 返回 MetaMask confirm() 参数

### Escrow 状态机
```
created → funded → executing → delivered → verified → released
                        → disputed → resolved_refund / resolved_release
                        → expired → (auto-release)
            → seller_timeout → refunded_timeout
```

| 状态 | 说明 |
|------|------|
| created | 已创建，等待买家锁资金 |
| funded | 买家已锁资金，等待卖家接单 |
| executing | 卖家正在执行 |
| delivered | 卖家已提交交付 |
| verified | 验证门通过 (off-chain) |
| released | 资金已释放给卖家 (终态) |
| disputed | 进入争议窗口 |
| resolved_refund | 仲裁退款给买家 (终态) |
| resolved_release | 仲裁释放给卖家 (终态) |
| expired | 验收超时，自动释放 (终态) |
| refunded_timeout | 卖家超时，退款 (终态) |

---

## Session Key 授权 API

通过 Node.js 代理访问：`/api/v1/protocol/session-keys/*`

### 创建 Session Key
```
POST /api/v1/protocol/session-keys/create
```
```json
{
  "main_wallet": "0x...",
  "main_private_key": "0x... (或 DEMO 占位符)",
  "agent_id": "agent-001",
  "chains": ["bsc", "mock"],
  "per_tx_limit": "0.5",
  "total_quota": "10",
  "actions": ["pay", "escrow", "deliver"],
  "validity_seconds": 86400
}
```

### 获取 Session Key 信息 (不含私钥)
```
GET /api/v1/protocol/session-keys/:keyId
```

### 撤销 Session Key
```
POST /api/v1/protocol/session-keys/:keyId/revoke
```
```json
{
  "main_wallet": "0x...",
  "main_private_key": "0x... (或 DEMO)"
}
```

### 增加总额度
```
POST /api/v1/protocol/session-keys/:keyId/increase-quota
```
```json
{
  "additional_quota": "5.0",
  "main_wallet": "0x...",
  "main_private_key": "0x... (或 DEMO)"
}
```

### 获取 Agent 的 Session Keys
```
GET /api/v1/protocol/session-keys/agent/:agentId
```

---

## Demo 模式

设置 `DEMO_MODE=true` 可跳过：
- 链上支付验证
- 押金检查
- API endpoint 预检

方便评委快速体验完整流程。
