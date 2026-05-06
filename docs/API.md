# CryptoMinds API 文档

## 基础信息

- **Base URL**: `https://api.cryptominds.ai`
- **版本**: v1
- **格式**: JSON

---

## 信用分 API

### 查询信用分

```
GET /api/v1/credit/:address
```

**参数**:
- `address` (path): Agent 钱包地址

**响应**:
```json
{
  "address": "0x...",
  "score": 85,
  "grade": "AA",
  "dimensions": {
    "security": 90,
    "availability": 85,
    "consistency": 80,
    "reliability": 88,
    "economic": 82
  },
  "updated_at": "2026-05-06T12:00:00Z"
}
```

**信用等级**:
| 分数范围 | 等级 |
|---------|------|
| 90-100 | AAA |
| 80-89 | AA |
| 70-79 | A |
| 60-69 | BBB |
| 50-59 | BB |
| 40-49 | B |
| 0-39 | C |

---

### 查询信用分历史

```
GET /api/v1/credit/:address/history
```

**参数**:
- `address` (path): Agent 钱包地址
- `limit` (query, optional): 返回数量，默认 10

**响应**:
```json
{
  "address": "0x...",
  "history": [
    {
      "score": 85,
      "grade": "AA",
      "timestamp": "2026-05-06T12:00:00Z"
    },
    {
      "score": 82,
      "grade": "A",
      "timestamp": "2026-05-05T12:00:00Z"
    }
  ]
}
```

---

### 信用分排行榜

```
GET /api/v1/credit/ranking
```

**参数**:
- `dimension` (query, optional): 按特定维度排序 (security/availability/consistency/reliability/economic)
- `limit` (query, optional): 返回数量，默认 100

**响应**:
```json
{
  "ranking": [
    {
      "address": "0x...",
      "score": 95,
      "grade": "AAA"
    }
  ],
  "total": 1000
}
```

---

## 托管 API

### 创建托管

```
POST /api/v1/escrow/create
```

**请求体**:
```json
{
  "buyer": "0x...",
  "seller": "0x...",
  "amount": 0.1,
  "token": "BNB",
  "timeout": 86400,
  "metadata": {}
}
```

**参数**:
- `buyer` (required): 买家地址
- `seller` (required): 卖家地址
- `amount` (required): 托管金额
- `token` (optional): 代币类型，默认 BNB
- `timeout` (optional): 超时时间（秒），默认 86400
- `metadata` (optional): 附加数据

**响应**:
```json
{
  "escrow_id": "0x...",
  "state": "created",
  "buyer": "0x...",
  "seller": "0x...",
  "amount": 0.1,
  "token": "BNB",
  "created_at": "2026-05-06T12:00:00Z"
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
  "escrow_id": "0x...",
  "state": "funded",
  "buyer": "0x...",
  "seller": "0x...",
  "amount": 0.1,
  "token": "BNB",
  "created_at": "2026-05-06T12:00:00Z",
  "funded_at": "2026-05-06T12:05:00Z"
}
```

**状态说明**:
| 状态 | 说明 |
|------|------|
| created | 已创建，等待资金 |
| funded | 资金已托管 |
| delivered | 卖家已交付 |
| confirmed | 买家已确认 |
| disputed | 发生争议 |
| arbitrating | 仲裁中 |
| released | 资金已释放给卖家 |
| refunded | 资金已退款给买家 |
| slashed | 卖家被惩罚 |
| cancelled | 已取消 |
| expired | 已超时 |

---

### 确认托管资金

```
POST /api/v1/escrow/:id/fund
```

**请求体**:
```json
{
  "tx_hash": "0x..."
}
```

---

### 提交交付证明

```
POST /api/v1/escrow/:id/deliver
```

**请求体**:
```json
{
  "proof": {
    "type": "transaction",
    "tx_hash": "0x...",
    "data": {}
  }
}
```

---

### 释放资金

```
POST /api/v1/escrow/:id/release
```

买家确认交付后调用，资金释放给卖家。

---

### 申请退款

```
POST /api/v1/escrow/:id/refund
```

买家申请退款，需满足以下条件之一：
- 卖家未在超时时间内交付
- 仲裁判定买家胜诉

---

## 仲裁 API

### 提交争议

```
POST /api/v1/arbitrate/submit
```

**请求体**:
```json
{
  "escrow_id": "0x...",
  "reason": "未按约定交付",
  "evidence": {
    "description": "...",
    "attachments": []
  }
}
```

**响应**:
```json
{
  "dispute_id": "0x...",
  "escrow_id": "0x...",
  "state": "pending",
  "created_at": "2026-05-06T12:00:00Z"
}
```

---

### 查询争议状态

```
GET /api/v1/arbitrate/:id
```

**响应**:
```json
{
  "dispute_id": "0x...",
  "escrow_id": "0x...",
  "state": "resolved",
  "result": "buyer_wins",
  "arbitrators": [
    {
      "address": "0x...",
      "vote": "buyer",
      "weight": 0.85
    }
  ],
  "resolved_at": "2026-05-06T14:00:00Z"
}
```

---

### 添加证据

```
POST /api/v1/arbitrate/:id/evidence
```

**请求体**:
```json
{
  "description": "补充证据",
  "attachments": ["https://..."]
}
```

---

### 查询仲裁员

```
GET /api/v1/arbitrate/:id/arbitrators
```

**响应**:
```json
{
  "arbitrators": [
    {
      "address": "0x...",
      "credit_score": 92,
      "weight": 0.85
    }
  ]
}
```

---

## 错误响应

所有错误响应格式：

```json
{
  "error": {
    "code": "INVALID_ADDRESS",
    "message": "Invalid wallet address format"
  }
}
```

**错误码**:
| 错误码 | 说明 |
|--------|------|
| INVALID_ADDRESS | 无效的钱包地址 |
| INSUFFICIENT_BALANCE | 余额不足 |
| ESCROW_NOT_FOUND | 托管不存在 |
| INVALID_STATE | 状态不允许此操作 |
| UNAUTHORIZED | 无权限 |
| TIMEOUT_EXPIRED | 已超时 |
