# CryptoMinds API 文档

## 基础信息

- **统一入口**: `http://localhost:3457` (Node.js)
- **协议层**: `http://localhost:3458` (Python，内部微服务)
- **链**: BNB Chain (BSC), ETH, Solana, Mock
- **合约**: `0x1A81a18dFC26676AC30f95f4659Fe4c0b4355EC3`

---

## 架构说明

```
客户端 → Node.js (3457) → Python (3458)
              ↓
           SQLite
```

- Node.js 处理市场、订单、通知等业务逻辑
- Python 处理协议层（验证门、结算通道、Agent 注册）
- `/api/protocol/*` 路由自动代理到 Python

---

## 市场 API

### 获取卖家列表
```
GET /api/sellers
```
返回所有已激活的卖家服务。

### 获取市场信息
```
GET /api/market
```
返回市场统计信息。

### 获取余额
```
GET /api/balance?wallet=0x...
```

### 获取购买记录
```
GET /api/purchases?wallet=0x...
```

### 购买服务
```
POST /api/purchases/create
```
```json
{
  "sellerId": "seller-001",
  "buyerWallet": "0x...",
  "buyerName": "买家名称",
  "price": 0.001,
  "input": "帮我买 1 BNB 的币"
}
```

### 获取我的订单
```
GET /api/purchases?wallet=0x...
```

### 确认收货
```
POST /api/purchases/confirm/:orderId
```
- 如果订单走合约托管，前端需先调用合约 `confirm(escrowOrderId)`
- 后端更新评分和状态

---

## 卖家 API

### 入驻申请
```
POST /api/sellers/register
```
```json
{
  "name": "Meme 狙击手",
  "description": "根据自己的策略执行 meme 买入并交付代币",
  "wallet": "0x...",
  "price": 0.001,
  "deposit": 0.1,
  "apiEndpoint": "https://..."
}
```

### 提交交付结果
```
POST /api/orders/:orderId/result
```
```json
{
  "output": "已自主选定 meme 并完成买入，代币已转入买家钱包",
  "sellerWallet": "0x...",
  "deliveryTxHash": "0x..."
}
```
- 如果订单有 `escrowOrderId`，前端需先调用合约 `deliver(escrowOrderId, result)`

### 获取卖家订单
```
GET /api/orders?sellerWallet=0x...
```

---

## Escrow 合约 API

### 获取合约信息
```
GET /api/escrow/info
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
GET /api/escrow/stats
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
GET /api/escrow/order/:orderId
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
POST /api/agents/register
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
GET /api/agents
```

### Agent 自主下单
```
POST /api/agent-buy
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

通过 Node.js 代理访问：`/api/protocol/*`

### 协议信息
```
GET /api/protocol/info
```

### 结算通道列表
```
GET /api/protocol/channels
```

### 验证门列表
```
GET /api/protocol/gates
```

### 创建任务
```
POST /api/protocol/tasks/create
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
POST /api/protocol/tasks/verify
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
GET /api/notifications?wallet=0x...
```

### 标记已读
```
POST /api/notifications/:id/read
```

---

## 管理员 API

需要 `X-Admin-Secret` header 或 `secret` query 参数。

### 获取待审核卖家
```
GET /api/admin/pending-sellers?secret=xxx
```

### 审核通过
```
POST /api/admin/approve-seller?secret=xxx
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

通过 Node.js 代理访问：`/api/protocol/escrow/*`

### 创建 Escrow 托管订单 (需 ADMIN_SECRET)
```
POST /api/protocol/escrow/create
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
GET /api/protocol/escrow/:escrowId
```

### 发起争议
```
POST /api/protocol/escrow/:escrowId/dispute
```
```json
{
  "reason": "交付质量不达标",
  "initiator": "buyer"
}
```

### 管理员仲裁 (需 ADMIN_SECRET)
```
POST /api/protocol/escrow/:escrowId/resolve
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
GET /api/protocol/escrow/disputed
```

### Escrow 正向路径 (生命周期端点)

#### 准备链上锁定 (返回 MetaMask 参数)
```
POST /api/protocol/escrow/:escrowId/fund/prepare
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
POST /api/protocol/escrow/:escrowId/fund/confirm
```
```json
{
  "on_chain_order_id": "0x...",
  "reason": "链上锁定确认"
}
```

#### 卖家接单 (FUNDED → EXECUTING)
```
POST /api/protocol/escrow/:escrowId/seller-accept
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
POST /api/protocol/escrow/:escrowId/deliver
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
POST /api/protocol/escrow/:escrowId/verify
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
POST /api/protocol/escrow/:escrowId/release
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

通过 Node.js 代理访问：`/api/protocol/session-keys/*`

### 创建 Session Key
```
POST /api/protocol/session-keys/create
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
GET /api/protocol/session-keys/:keyId
```

### 撤销 Session Key
```
POST /api/protocol/session-keys/:keyId/revoke
```
```json
{
  "main_wallet": "0x...",
  "main_private_key": "0x... (或 DEMO)"
}
```

### 增加总额度
```
POST /api/protocol/session-keys/:keyId/increase-quota
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
GET /api/protocol/session-keys/agent/:agentId
```

---

## Demo 模式

设置 `DEMO_MODE=true` 可跳过：
- 链上支付验证
- 押金检查
- API endpoint 预检

方便评委快速体验完整流程。
