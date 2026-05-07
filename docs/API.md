# CryptoMinds API 文档

## 基础信息

- **Base URL**: `http://localhost:3458` (本地开发)
- **生产 URL**: 待部署
- **版本**: v1
- **格式**: JSON

---

## 信用分 API

### 查询信用分

```
GET /api/v1/credit/:agent_id
```

**参数**:
- `agent_id` (path): Agent ID（如 agent_high_0001）

**响应**:
```json
{
  "agent_id": "agent_high_0001",
  "wallet": "0x...",
  "total_score": 864.6,
  "grade": "AAA",
  "dimensions": {
    "S": {"name": "Stability", "score": 175.2},
    "A": {"name": "Activity", "score": 168.4},
    "C": {"name": "Creditworthiness", "score": 172.8},
    "R": {"name": "Reliability", "score": 178.6},
    "E": {"name": "Ecosystem", "score": 169.6}
  },
  "record_count": 245,
  "updated_at": "2026-05-07T12:00:00Z"
}
```

**信用等级**:
| 分数范围 | 等级 |
|---------|------|
| 850+ | AAA |
| 750-849 | AA |
| 650-749 | A |
| 550-649 | BBB |
| 450-549 | BB |
| 350-449 | B |
| <350 | C |

---

### 信用分排行榜

```
GET /api/v1/credit/ranking
```

**参数**:
- `limit` (query, optional): 返回数量，默认 50

**响应**:
```json
{
  "ranking": [
    {
      "agent_id": "agent_high_0001",
      "wallet": "0x...",
      "total_score": 864.6,
      "grade": "AAA"
    }
  ],
  "total": 40
}
```

---

## 托管 API

### 预览押金折扣

```
POST /api/v1/escrow/discount-preview
```

**请求体**:
```json
{
  "seller": "agent_high_0001",
  "amount": 1.0
}
```

**响应**:
```json
{
  "credit_score": 864.6,
  "credit_grade": "AAA",
  "discount_rate": 0.7,
  "discount_percent": "30%",
  "required_deposit": 0.7,
  "original_deposit": 1.0,
  "savings": 0.3
}
```

---

### 创建托管

```
POST /api/v1/escrow/create
```

**请求体**:
```json
{
  "buyer": "buyer_001",
  "seller": "agent_high_0001",
  "amount": 1.0
}
```

**响应**:
```json
{
  "escrow_id": "escrow_abc123",
  "state": "pending",
  "buyer": "buyer_001",
  "seller": "agent_high_0001",
  "amount": 1.0,
  "required_deposit": 0.7,
  "credit_discount": {
    "seller_grade": "AAA",
    "discount_percent": "30%",
    "savings": 0.3
  },
  "created_at": "2026-05-07T12:00:00Z"
}
```

---

### 查询托管状态

```
GET /api/v1/escrow/:id
```

**响应**:
```json
{
  "escrow_id": "escrow_abc123",
  "state": "funded",
  "buyer": "buyer_001",
  "seller": "agent_high_0001",
  "amount": 1.0,
  "created_at": "2026-05-07T12:00:00Z",
  "funded_at": "2026-05-07T12:05:00Z"
}
```

**状态说明**:
| 状态 | 说明 |
|------|------|
| pending | 已创建，等待资金 |
| funded | 资金已托管 |
| delivered | 卖家已交付 |
| disputed | 发生争议 |
| settled | 已结算 |
| refunded | 已退款 |

---

## Voucher API

### 预览额度上限

```
POST /api/v1/voucher/limit-preview
```

**请求体**:
```json
{
  "agent_id": "agent_high_0001"
}
```

**响应**:
```json
{
  "agent_id": "agent_high_0001",
  "credit_score": 864.6,
  "credit_grade": "AAA",
  "multiplier": "5x",
  "max_limit": 500,
  "base_limit": 100
}
```

---

## 仲裁 API

### 预览仲裁权重

```
POST /api/v1/arbitrate/weight-preview
```

**请求体**:
```json
{
  "arbitrator": "agent_high_0001"
}
```

**响应**:
```json
{
  "arbitrator": "agent_high_0001",
  "credit_score": 864.6,
  "credit_grade": "AAA",
  "weight_multiplier": 1.68,
  "base_weight": 1.0,
  "effective_weight": 1.68
}
```

---

### 提交争议

```
POST /api/v1/arbitrate/submit
```

**请求体**:
```json
{
  "escrow_id": "escrow_abc123",
  "reason": "未按约定交付"
}
```

**响应**:
```json
{
  "dispute_id": "dispute_xyz789",
  "escrow_id": "escrow_abc123",
  "state": "pending",
  "created_at": "2026-05-07T12:00:00Z"
}
```

---

### 仲裁员投票

```
POST /api/v1/arbitrate/:dispute_id/vote
```

**请求体**:
```json
{
  "arbitrator": "agent_high_0001",
  "vote": "buyer_wins"
}
```

**响应**:
```json
{
  "dispute_id": "dispute_xyz789",
  "arbitrator": "agent_high_0001",
  "vote": "buyer_wins",
  "weight": 1.68,
  "credited": true
}
```

---

## 错误响应

所有错误响应格式：

```json
{
  "error": "错误描述"
}
```

**常见错误**:
| 错误 | 说明 |
|------|------|
| Agent not found | Agent 不存在 |
| Invalid amount | 无效金额 |
| Escrow not found | 托管不存在 |
| Invalid state | 状态不允许此操作 |
