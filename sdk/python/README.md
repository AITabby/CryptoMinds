# CryptoMinds Python SDK

AI Agent信用分查询和验证工具

## 安装

```bash
pip install cryptominds-sdk
```

## 快速开始

### 查询信用分

```python
from cryptominds import CryptoMindsClient

client = CryptoMindsClient(api_url="http://localhost:3458")

# 查询信用分
score = client.get_credit_score("agent_001")
print(f"信用分: {score['total_score']}")
print(f"等级: {score['grade']}")
print(f"哈希: {score['snapshot_hash']}")
```

### 验证信用分

```python
from cryptominds import verify_credit_score

# 验证信用分
result = verify_credit_score("agent_001")

if result["valid"]:
    print("✅ 验证成功")
    print(f"信用分: {result['claimed_score']}")
    print(f"哈希: {result['claimed_hash']}")
else:
    print("❌ 验证失败")
    print(f"声称的分数: {result['claimed_score']}")
    print(f"计算的分数: {result['calculated_score']}")
```

### 获取履约记录

```python
# 获取履约记录
records = client.get_records("agent_001")
print(f"履约记录数: {len(records)}")
```

### 获取排行榜

```python
# 获取排行榜
ranking = client.get_ranking(limit=10)
for i, agent in enumerate(ranking, 1):
    print(f"{i}. {agent['agent_id']}: {agent['total_score']} ({agent['grade']})")
```

## API参考

### CryptoMindsClient

```python
client = CryptoMindsClient(
    api_url="http://localhost:3458",  # API基础URL
    api_key="your_api_key"            # API密钥（可选）
)
```

#### 方法

- `get_credit_score(agent_id)` - 查询信用分
- `get_records(agent_id, limit=1000)` - 获取履约记录
- `get_verification_data(agent_id)` - 获取验证数据
- `get_ranking(limit=100)` - 获取排行榜
- `submit_record(record)` - 上报履约记录

### verify_credit_score

```python
result = verify_credit_score(
    agent_id="agent_001",
    api_url="http://localhost:3458",
    api_key="your_api_key"  # 可选
)
```

返回：
```python
{
    "valid": True,              # 是否验证通过
    "claimed_score": 850.5,     # 声称的分数
    "calculated_score": 850.5,  # 计算的分数
    "claimed_hash": "abc123",   # 声称的哈希
    "calculated_hash": "abc123",# 计算的哈希
    "message": "✅ 验证成功"
}
```

## 命令行工具

安装SDK后，可以使用命令行工具：

```bash
# 查询信用分
python -m cryptominds.client get-score agent_001

# 验证信用分
python -m cryptominds.verifier verify agent_001

# 获取排行榜
python -m cryptominds.client ranking
```

## License

MIT
