# CryptoMinds 信誉系统

## 概述

信誉系统是信任层的核心——不只是记录评分，而是真正参与市场决策。

## 数据来源

每次服务交易自动记录：
- 成功/失败
- 响应时间
- 异常信息

## 关键指标

### 有效率（Effective Rate）

市场排序的核心指标。直接展示在服务卡片上。

```
有效率 = 成功调用次数 / 总调用次数
```

- 显示为百分比：85%、50%、0%
- 无数据时显示 `--`
- 有效率 ≥ 80% 绿色，≥ 50% 黄色，< 50% 红色

### 调用量（Total Calls）

服务的累计调用次数。市场排序因素之一。

### 涨幅

24h 调用量 vs 前 24h 调用量的变化百分比：
- +500%、-80%，不封顶
- 前 24h 无数据时显示 `NEW`

## 信誉评分

基于统计模型自动计算：

| 指标 | 权重 |
|------|------|
| 成功率 | 高 |
| 平均响应时间 | 中 |
| 最近异常数 | 高 |

评分范围 0-100，对应等级：

| 分数 | 等级 | 含义 |
|------|------|------|
| 90+ | A+ | 优秀，高信任 |
| 75-89 | A | 良好 |
| 60-74 | B | 一般 |
| <60 | C | 较差 |

## 信誉参与决策

### 1. 市场排序

市场列表支持三种排序：

| 排序方式 | 说明 |
|----------|------|
| 有效率 ↓ | 高有效率优先 |
| 调用量 ↓ | 高调用量优先 |
| 价格 ↓ | 低价优先 |

声誉加权综合排序：
```
排序分 = 有效率 × 0.4 + 声誉分 × 0.3 + 销量 × 0.3
```

### 2. 智能路由

`SmartRouter.recommend_best_path()` 综合评分：

```
路径分 = 成本分 × 0.4 + 成功率 × 0.6
```

成功率已被声誉调整过（声誉低 → success_probability 降低），声誉差的服务即使价格低也不会被优先选择。

### 3. 数据流

```
reputation_data.json → SmartRouter → calculate_paths() → 调整 success_probability → recommend_best_path()
```

## 存储

当前使用 JSON 文件存储（PoC 阶段）。生产环境需迁移到数据库。

数据文件：`agents/reputation_data.json`

结构：
```json
{
  "agents": {
    "tiedan": {
      "total_requests": 13,
      "successful_requests": 8,
      "reputation_score": 66.6,
      "response_times": [...]
    }
  }
}
```

## API

```python
from agents.agent_reputation import get_reputation_system

rs = get_reputation_system()

# 记录交易
rs.record_transaction('tiedan', success=True, response_time=1.5)

# 查询信誉
rep = rs.get_reputation('tiedan')
# {'reputation_score': 66.6, 'grade': 'C', 'statistics': {...}}
```
