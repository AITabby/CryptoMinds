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

## 信任网络 API

### 获取信任网络数据

```
GET /api/v1/trust-network
```

**参数**:
- `limit` (query, optional): 返回交易数量，默认 500，最大 2000

**响应**:
```json
{
  "nodes": [
    {
      "id": "0x...",
      "type": "buyer",
      "transactions": 15,
      "volume": 12.5,
      "credit_score": 850,
      "credit_grade": "AAA"
    }
  ],
  "edges": [
    {
      "source": "0x...",
      "target": "0x...",
      "amount": "1.0",
      "success": true,
      "timestamp": 1715040000
    }
  ],
  "stats": {
    "total_nodes": 50,
    "total_edges": 120
  }
}
```

---

### 查询信任路径

```
GET /api/v1/trust-path/:from_agent/:to_agent
```

**参数**:
- `from_agent` (path): 起始 Agent ID
- `to_agent` (path): 目标 Agent ID
- `max_depth` (query, optional): 最大搜索深度，默认 4，最大 6

**响应**:
```json
{
  "from": "agent_high_0001",
  "to": "agent_low_0010",
  "path": [
    {"agent_id": "agent_high_0001", "credit_score": 864.6, "credit_grade": "AAA"},
    {"agent_id": "agent_mid_0005", "credit_score": 720.0, "credit_grade": "A"},
    {"agent_id": "agent_low_0010", "credit_score": 450.0, "credit_grade": "BB"}
  ],
  "found": true
}
```

**应用场景**:
- Agent A 想信任 Agent D，但没直接交易过
- 如果 A→B→C→D 有成功交易链，A 可间接信任 D
- 类似 LinkedIn "二度人脉"

---

### 获取综合信任评分

```
GET /api/v1/trust-score/:agent_id
```

**参数**:
- `agent_id` (path): 目标 Agent ID
- `from` (query, optional): 查询者 Agent ID，用于计算间接信任

**响应**:
```json
{
  "agent_id": "agent_low_0010",
  "direct_score": 450.0,
  "trust_path": [
    {"agent_id": "agent_high_0001", "credit_score": 864.6, "credit_grade": "AAA"},
    {"agent_id": "agent_mid_0005", "credit_score": 720.0, "credit_grade": "A"}
  ],
  "path_length": 2,
  "indirect_score": 632.4,
  "combined_score": 578.4
}
```

**评分说明**:
| 字段 | 说明 |
|------|------|
| direct_score | 直接信用分（SACRED分数）|
| indirect_score | 间接信任分（信任路径加权）|
| combined_score | 综合信任分（直接60% + 间接40%）|

**间接信任计算**:
- 路径上节点信用分平均值
- 路径越长，信任衰减越大（0.8^(路径长度-1)）

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
