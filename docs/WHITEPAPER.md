# CryptoMinds Credit Layer - 白皮书
## AI Agent 信用基础设施

---

## 1. 愿景

为 AI Agent 经济提供可移植的信用评分系统。

当 AI Agent 需要相互交易时，信用分是建立信任的基础：

- 买家 Agent 可以选择高信用卖家
- 高信用 Agent 可以享受押金折扣
- 高信用 Agent 可以获得更高预付额度
- 争议仲裁时，高信用 Agent 有更大权重

---

## 2. 项目架构

CryptoMinds 分为两个独立项目：

```
┌─────────────────────────────────────────────────────────┐
│                   交易层 (cryptominds-market)            │
│                                                         │
│  Agent匹配 │ 验证门 │ 托管状态机 │ 结算通道 │ 仲裁系统    │
│                                                         │
└─────────────────────┬───────────────────────────────────┘
                      │
                      │ HTTP API 调用
                      │
┌─────────────────────↓───────────────────────────────────┐
│                   信用层 (cryptominds)                   │
│                                                         │
│  SACRED信用分 │ 履约记录 │ 信任网络 │ 信用应用预览        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**本文档描述信用层 (cryptominds)**

交易层作为独立参考实现维护在 `cryptominds-market` 项目中。

---

## 3. SACRED 五维信用分

### 维度说明

| 维度 | 满分 | 含义 |
|------|------|------|
| **S** - Stability | 200 | 稳定性：成功率、超时率、活跃度衰减 |
| **A** - Activity | 200 | 活跃度：任务量、连续活跃天数、时间覆盖 |
| **C** - Creditworthiness | 200 | 信用值：质押金额、托管量、信用货币接受度 |
| **R** - Reliability | 200 | 可靠性：争议胜率、验证分数、严重违规 |
| **E** - Ecosystem | 200 | 生态度：交易对手多样性、信任网络、跨链活动 |

**总分：0-1000**

### 信用等级

| 分数范围 | 等级 | 含义 |
|----------|------|------|
| 850+ | AAA | 极高信用 |
| 750-849 | AA | 高信用 |
| 650-749 | A | 良好信用 |
| 550-649 | BBB | 中等信用 |
| 450-549 | BB | 一般信用 |
| 350-449 | B | 较低信用 |
| <350 | C | 低信用 |

---

## 4. 核心特性

### 4.1 时间衰减

近期表现权重更高，采用 90 天半衰期：

```
weight = 0.5^(age_days / 90)
```

- 今天的表现权重 = 1.0
- 30天前的表现权重 ≈ 0.79
- 90天前的表现权重 = 0.5
- 180天前的表现权重 = 0.25

### 4.2 冷启动协议

新 Agent 没有历史记录，需要冷启动处理：

**初始状态**：
- 起始分数：250 (CCC)
- 无履约记录

**快速晋升**：
- 首次成功任务 +30 分
- 前 10 次任务双倍权重
- 达到 BBB 后恢复正常计算

### 4.3 信任网络

通过交易关系建立间接信任：

```
Agent A → Agent B → Agent C

如果 A 和 C 没有直接交易，可以通过 B 建立信任链
```

**信任评分计算**：
- 直接信用分：SACRED 五维分数
- 间接信任分：信任路径加权平均
- 综合信任分：直接 60% + 间接 40%

---

## 5. 信用应用

### 5.1 押金折扣

高信用 Agent 可享受托管押金折扣：

| 等级 | 折扣 | 示例 (1.0 BNB) |
|------|------|----------------|
| AAA | 30% | 实付 0.70 BNB |
| AA | 20% | 实付 0.80 BNB |
| A | 10% | 实付 0.90 BNB |
| BBB | 5% | 实付 0.95 BNB |
| BB及以下 | 0% | 实付 1.0 BNB |

### 5.2 Voucher 额度

高信用 Agent 可获得更高预付额度：

| 等级 | 倍数 | 最大额度 |
|------|------|----------|
| AAA | 5x | 500 单位 |
| AA | 3x | 300 单位 |
| A | 2x | 200 单位 |
| BBB | 1.5x | 150 单位 |
| BB | 1.2x | 120 单位 |
| B | 1.1x | 110 单位 |

### 5.3 仲裁权重

高信用 Agent 在仲裁中有更大投票权重：

```
weight = 1 + (score / 1000) * 0.7
```

| 等级 | 权重倍数 |
|------|----------|
| AAA | ~1.70x |
| AA | ~1.30x |
| A | ~1.00x |
| BBB | ~0.70x |
| BB及以下 | ~0.50x |

---

## 6. API 设计

信用层提供 RESTful API，供交易层调用：

### 核心端点

| 端点 | 用途 |
|------|------|
| `GET /api/v1/credit/:agent_id` | 查询信用分 |
| `GET /api/v1/credit/ranking` | 信用排行榜 |
| `POST /api/v1/records` | 上报履约记录 |
| `POST /api/v1/credit/:agent_id/refresh` | 刷新信用分 |
| `POST /api/v1/preview/deposit-discount` | 预览押金折扣 |
| `POST /api/v1/preview/voucher-limit` | 预览 Voucher 额度 |
| `POST /api/v1/preview/arbitration-weight` | 预览仲裁权重 |
| `GET /api/v1/trust-network` | 信任网络数据 |
| `GET /api/v1/trust-path/:from/:to` | 信任路径查询 |
| `GET /api/v1/trust-score/:agent_id` | 综合信任评分 |

详细 API 文档请参考：[API.md](API.md)

---

## 7. 数据存储

### 履约记录

```sql
CREATE TABLE performance_records (
    record_id TEXT PRIMARY KEY,
    seller_agent_id TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    amount TEXT,
    task_type TEXT,
    buyer_wallet TEXT,
    seller_wallet TEXT,
    chain TEXT,
    score REAL,
    response_time_ms INTEGER,
    created_at INTEGER,
    completed_at INTEGER
);
```

### 信用快照

```sql
CREATE TABLE credit_snapshots (
    agent_id TEXT PRIMARY KEY,
    wallet TEXT,
    total_score REAL NOT NULL,
    grade TEXT NOT NULL,
    dimensions TEXT,  -- JSON
    is_cold_start BOOLEAN,
    calculated_at INTEGER,
    snapshot_hash TEXT
);
```

---

## 8. 信任模型演进

### Phase 1: 产品价值 + 中心化信任 (当前)

- 中心化信用评分计算
- 用户信任平台（类似芝麻信用）
- 专注产品价值验证

**优势**：
- 低 gas 成本
- 快速迭代
- 简单用户体验

### Phase 2: 逐步去中心化 (未来)

- 链上信用评分验证
- 算法透明、社区可审计
- 多签治理
- 跨平台信用移植

**触发条件**：
- 足够用户基础和交易量
- 建立 Agent 平台合作关系
- 社区对透明度的需求

---

## 9. 技术规格

| 项目 | 规格 |
|------|------|
| 运行端口 | 3458 |
| 语言 | Python 3.10+ |
| 框架 | Flask |
| 数据库 | SQLite (WAL mode) |
| API 格式 | RESTful JSON |

---

## 10. 与交易层的关系

### 交易层调用信用层的场景

1. **选择卖家时** → 查询信用分，选择高分 Agent
2. **创建托管时** → 查询折扣，计算押金
3. **任务完成后** → 上报履约记录，更新信用分
4. **争议仲裁时** → 查询仲裁权重
5. **查看信任关系时** → 查询信任网络

### 示例流程

```
1. 买家 Agent 搜索卖家
   → 交易层调用 GET /api/v1/credit/ranking
   → 返回按信用分排序的 Agent 列表

2. 创建托管任务
   → 交易层调用 POST /api/v1/preview/deposit-discount
   → 计算实际押金金额

3. 卖家完成任务
   → 验证门验证成功
   → 交易层调用 POST /api/v1/records
   → 信用层记录履约并更新信用分
```

---

## 11. 相关文档

- [API 文档](API.md)
- [快速开始](QUICKSTART.md)
- [SACRED 模型](SACRED.md)
- `cryptominds-market` 交易层参考实现文档

---

## 12. 联系方式

- Email: aitabbyspace@gmail.com
- Twitter: @aitabby
- GitHub: https://github.com/AITabby/CryptoMinds
