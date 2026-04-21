# CryptoMinds API 文档

## 基础信息

- **Base URL**: `http://localhost:3457`
- **链**: BNB Chain (BSC)
- **合约**: `0x1A81a18dFC26676AC30f95f4659Fe4c0b4355EC3`

---

## 买家 API

### 获取卖家列表
```
GET /api/sellers
```
返回所有已激活的卖家服务。

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
  "input": "帮我买一个值得关注的 meme 币"
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
  "output": "已买入目标 meme 代币并转入买家钱包",
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

## Demo 模式

设置 `DEMO_MODE=true` 可跳过：
- 链上支付验证
- 押金检查
- API endpoint 预检

方便评委快速体验完整流程。
