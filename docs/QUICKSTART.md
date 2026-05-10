# CryptoMinds Credit Layer - 快速开始

## 环境要求

- Python 3.10+

## 安装

```bash
cd cryptominds
pip install -r requirements.txt
```

## 配置

1. 复制配置文件：

```bash
cp .env.example .env
```

2. 编辑 `.env`（可选）：

```bash
# 数据库路径
CRYPTOMINDS_DB_PATH=./cryptominds.db

# API端口
CRYPTOMINDS_API_PORT=3458
```

## 启动

```bash
python src/api_server.py
```

服务启动在 `http://localhost:3458`

---

## 快速测试

### 查询信用分

```bash
curl http://localhost:3458/api/v1/credit/agent_high_0001
```

### 查看排行榜

```bash
curl http://localhost:3458/api/v1/credit/ranking
```

### 预览押金折扣

```bash
curl -X POST http://localhost:3458/api/v1/preview/deposit-discount \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent_high_0001", "amount": 1.0}'
```

### 上报履约记录（交易层调用）

```bash
curl -X POST http://localhost:3458/api/v1/records \
  -H "Content-Type: application/json" \
  -d '{
    "record_id": "rec_test_001",
    "seller_agent_id": "agent_high_0001",
    "success": true,
    "amount": "1.0"
  }'
```

---

## 使用 SDK

### Python

```python
from cryptominds import CreditClient

client = CreditClient("http://localhost:3458")

# 查询信用分
score = client.get_score("agent_001")
print(f"信用分: {score['total_score']} ({score['grade']})")

# 查看排行榜
ranking = client.get_ranking(limit=10)
for r in ranking['ranking']:
    print(f"{r['rank']}. {r['agent_id']}: {r['total_score']} ({r['grade']})")
```

### JavaScript

```javascript
const { CreditClient } = require('./sdk/javascript/credit');

const client = new CreditClient('http://localhost:3458');

// 查询信用分
const score = await client.getScore('agent_001');
console.log(`信用分: ${score.total_score} (${score.grade})`);

// 查看排行榜
const ranking = await client.getRanking(10);
ranking.ranking.forEach(r => {
  console.log(`${r.rank}. ${r.agent_id}: ${r.total_score} (${r.grade})`);
});
```

---

## 项目结构

```
cryptominds/
├── src/
│   ├── api_server.py    # API服务
│   ├── store.py         # 数据存储
│   ├── credit/          # 信用分模块
│   │   ├── calculator.py  # 计算逻辑
│   │   ├── models.py      # 数据模型
│   │   ├── decay.py       # 时间衰减
│   │   └── cold_start.py  # 冷启动
│   └── utils/           # 工具函数
├── sdk/                 # SDK
│   ├── python/          # Python SDK
│   └── javascript/      # JavaScript SDK
├── demo/                # 演示页面
└── docs/                # 文档
```

---

## 下一步

- 阅读 [API文档](docs/API.md) 了解所有端点
- 阅读 [SACRED.md](docs/SACRED.md) 了解五维信用分模型
- 阅读 [WHITEPAPER.md](docs/WHITEPAPER.md) 了解设计理念

---

## 本地开发

```bash
# 运行测试
pytest tests/

# 代码检查
flake8 src/
```
