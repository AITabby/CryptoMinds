# 快速开始

## 安装

### 本地开发（推荐）

```bash
# 克隆仓库
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds

# 安装依赖
pip install -r requirements.txt
```

### Python SDK（待发布）

```bash
# 尚未发布到 PyPI，请使用本地安装
pip install -e ./sdk/python
```

### JavaScript SDK（待发布）

```bash
# 尚未发布到 npm，请使用本地安装
npm link ./sdk/javascript
```

---

## 信用分查询

### Python

```python
from cryptominds import CreditClient

client = CreditClient()
score = client.get_score("0x...")
print(score)
# {"score": 85, "grade": "AA", "dimensions": {...}}
```

### JavaScript

```javascript
const { CreditClient } = require('cryptominds');

const client = new CreditClient();
const score = await client.getScore('0x...');
console.log(score);
```

---

## 创建托管

### Python

```python
from cryptominds import EscrowClient

escrow = EscrowClient()
result = escrow.create(
    buyer="0x...",
    seller="0x...",
    amount=0.1
)
print(result["escrow_id"])
```

### JavaScript

```javascript
const { EscrowClient } = require('cryptominds');

const escrow = new EscrowClient();
const result = await escrow.create({
  buyer: '0x...',
  seller: '0x...',
  amount: 0.1,
});
console.log(result.escrow_id);
```

---

## 提交争议

### Python

```python
from cryptominds import ArbitrationClient

arbitration = ArbitrationClient()
result = arbitration.submit(
    escrow_id="0x...",
    reason="未按约定交付",
    evidence={"description": "..."}
)
```

### JavaScript

```javascript
const { ArbitrationClient } = require('cryptominds');

const arbitration = new ArbitrationClient();
const result = await arbitration.submit({
  escrowId: '0x...',
  reason: '未按约定交付',
  evidence: { description: '...' },
});
```

---

## 完整流程示例

```python
from cryptominds import CreditClient, EscrowClient, ArbitrationClient

# 1. 查询卖家信用分
credit = CreditClient()
seller_score = credit.get_score("0x_seller")
print(f"卖家信用分: {seller_score['score']} ({seller_score['grade']})")

# 2. 创建托管
escrow = EscrowClient()
result = escrow.create(
    buyer="0x_buyer",
    seller="0x_seller",
    amount=0.1,
    timeout=86400  # 24小时
)
print(f"托管ID: {result['escrow_id']}")

# 3. 买家确认资金托管
escrow.fund(result["escrow_id"], "0x_tx_hash")

# 4. 卖家提交交付证明
escrow.deliver(result["escrow_id"], {
    "type": "transaction",
    "tx_hash": "0x_delivery_tx"
})

# 5. 买家确认交付
escrow.confirm(result["escrow_id"])
print("交易完成")
```

---

## 本地开发

```bash
# 克隆仓库
git clone https://github.com/cryptominds/cryptominds.git
cd cryptominds

# 安装依赖
pip install -r requirements.txt

# 启动 API 服务
python src/api_server.py

# 运行测试
pytest tests/
```
