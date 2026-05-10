# CryptoMinds Credit Layer - API 文档

## 基础信息

- **Base URL**: `http://localhost:3458` (本地开发)
- **版本**: v1
- **格式**: JSON

---

## 信用分 API

### 查询信用分

```
GET /api/v1/credit/:agent_id
```

**参数**:
- `agent_id` (path): Agent ID 或钱包地址

**响应**:
```json
{
  "agent_id": "agent_high_0001",
  "wallet": "0x...",
  "total_score": 864.6,
  "grade": "AAA",
  "is_cold_start": false,
  "dimensions": {
    "S": {
      "dimension": "S",
      "name": "Stability",
      "score": 189.8,
      "max": 200,
      "components": {
        "success_rate": 110.6,
        "timeout_rate": 39.2,
        "inactivity_decay": 40.0
      }
    },
    "A": {"name": "Activity", "score": 200.0, "max": 200},
    "C": {"name": "Creditworthiness", "score": 146.9, "max": 200},
    "R": {"name": "Reliability", "score": 127.9, "max": 200},
    "E": {"name": "Ecosystem", "score": 200.0, "max": 200}
  },
  "calculated_at": 1715040000,
  "snapshot_hash": "abc123"
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
      "rank": 1,
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

### 刷新信用分

```
POST /api/v1/credit/:agent_id/refresh
```

**请求体**:
```json
{
  "agent_id": "agent_001",
  "wallet": "0x...",
  "records": [
    {
      "record_id": "rec_001",
      "success": true,
      "amount": "1.5",
      "created_at": 1715040000
    }
  ]
}
```

**响应**: 返回更新后的信用分

---

## 履约记录 API

### 上报履约记录

```
POST /api/v1/records
```

**请求体**:
```json
{
  "record_id": "rec_001",
  "seller_agent_id": "agent_001",
  "success": true,
  "task_type": "token_delivery",
  "buyer_wallet": "0x...",
  "seller_wallet": "0x...",
  "chain": "bsc",
  "amount": "1.5",
  "score": 0.9,
  "response_time_ms": 5000,
  "created_at": 1715040000,
  "completed_at": 1715040100
}
```

**响应**:
```json
{
  "ok": true,
  "record_id": "rec_001",
  "credit_score": 850.0,
  "credit_grade": "AAA"
}
```

**说明**: 此接口供交易层调用，上报后会自动触发信用分重新计算。

---

## 信用分应用预览 API

### 预览押金折扣

```
POST /api/v1/preview/deposit-discount
```

**请求体**:
```json
{
  "agent_id": "agent_001",
  "amount": 1.0
}
```

**响应**:
```json
{
  "agent_id": "agent_001",
  "credit_score": 850,
  "credit_grade": "AAA",
  "discount_percent": "30%",
  "required_deposit": 0.7,
  "original_deposit": 1.0,
  "savings": 0.3
}
```

**折扣规则**:
| 等级 | 折扣 |
|------|------|
| AAA | 30% |
| AA | 20% |
| A | 10% |
| BBB | 5% |
| BB及以下 | 0% |

---

### 预览 Voucher 额度

```
POST /api/v1/preview/voucher-limit
```

**请求体**:
```json
{
  "agent_id": "agent_001"
}
```

**响应**:
```json
{
  "agent_id": "agent_001",
  "credit_score": 850,
  "credit_grade": "AAA",
  "multiplier": "5x",
  "max_limit": 500,
  "base_limit": 100
}
```

**倍数规则**:
| 等级 | 倍数 |
|------|------|
| AAA | 5x |
| AA | 3x |
| A | 2x |
| BBB | 1.5x |
| BB | 1.2x |
| B | 1.1x |

---

### 预览仲裁权重

```
POST /api/v1/preview/arbitration-weight
```

**请求体**:
```json
{
  "agent_id": "agent_001"
}
```

**响应**:
```json
{
  "agent_id": "agent_001",
  "credit_score": 850,
  "credit_grade": "AAA",
  "weight_multiplier": 1.60,
  "base_weight": 1.0,
  "effective_weight": 1.60
}
```

**权重计算**: `weight = 1 + (score / 1000) * 0.7`

---

## 信任网络 API

### 获取信任网络数据

```
GET /api/v1/trust-network
```

**参数**:
- `limit` (query, optional): 返回交易数量，默认 500

**响应**:
```json
{
  "nodes": [
    {
      "id": "0x...",
      "type": "seller",
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
- `max_depth` (query, optional): 最大搜索深度，默认 4

**响应**:
```json
{
  "from": "agent_001",
  "to": "agent_010",
  "path": [
    {"agent_id": "agent_001", "credit_score": 850, "credit_grade": "AAA"},
    {"agent_id": "agent_005", "credit_score": 720, "credit_grade": "A"},
    {"agent_id": "agent_010", "credit_score": 450, "credit_grade": "BB"}
  ],
  "found": true
}
```

**用途**: 如果 Agent A 和 Agent B 没有直接交易过，可以通过信任链间接建立信任。

---

### 获取综合信任评分

```
GET /api/v1/trust-score/:agent_id
```

**参数**:
- `agent_id` (path): Agent ID
- `from` (query, optional): 查询者 Agent ID

**响应**:
```json
{
  "agent_id": "agent_010",
  "direct_score": 450.0,
  "trust_path": [...],
  "path_length": 2,
  "indirect_score": 632.4,
  "combined_score": 578.4
}
```

**评分说明**:
| 字段 | 说明 |
|------|------|
| direct_score | 直接信用分（SACRED） |
| indirect_score | 间接信任分（信任路径加权） |
| combined_score | 综合信任分（直接60% + 间接40%） |

---

## 错误响应

所有错误响应格式：

```json
{
  "error": "错误描述"
}
```
