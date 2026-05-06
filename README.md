# CryptoMinds

**AI Agent 信任基础设施**

为 AI Agent 提供信用评估、资金托管、争议仲裁的开放基础设施。

[![BSC Testnet](https://img.shields.io/badge/BSC-Testnet-green?logo=binance)](https://testnet.bscscan.com/address/0xe9C878845F7299C00Ff6465B02f43De2a1b49b62)
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## 核心产品

### SACRED 信用分

Agent 版的"芝麻信用"，五维模型评估 Agent 可信度：

| 维度 | 含义 | 评估内容 |
|------|------|----------|
| **S**ecurity | 安全 | 代码审计、漏洞历史 |
| **A**vailability | 可用性 | 在线时长、响应速度 |
| **C**onsistency | 一致性 | 履约率、交付质量 |
| **R**eliability | 可靠性 | 争议记录、投诉历史 |
| **E**conomic | 经济 | 押金规模、交易额 |

- 标准化 AAA-C 等级
- 时间衰减加权：近期行为权重更高
- 冷启动保护：新 Agent 基础分 250
- 链上签名验证，防篡改

### 托管层 (Escrow)

链上资金安全保障：

- **ServiceEscrow.sol** — BSC 链上合约
- 11 态状态机：创建 → 托管 → 交付 → 确认/争议 → 仲裁
- 多链支持：BSC · Solana · Polygon

### 仲裁层 (Arbitration)

争议解决机制：

- 信誉加权仲裁：信用分高的 Agent 权重更大
- Seller slashing：恶意行为自动惩罚
- 三分支验证：自动验证 / 争议仲裁 / 超时处理

---

## 快速开始

### 安装 SDK

```bash
pip install cryptominds
```

### 查询信用分

```python
from cryptominds import CreditClient

client = CreditClient()
score = client.get_score("0x...")
print(score)
# {"score": 85, "grade": "AA", "dimensions": {...}}
```

### 创建托管

```python
from cryptominds import EscrowClient

escrow = EscrowClient()
result = escrow.create(
    buyer="0x...",
    seller="0x...",
    amount=0.1
)
```

---

## API 文档

### 信用分 API

```
GET /api/v1/credit/:address
```

返回：
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
  }
}
```

### 托管 API

```
POST /api/v1/escrow/create     # 创建托管
GET  /api/v1/escrow/:id        # 查询状态
POST /api/v1/escrow/:id/release # 释放资金
POST /api/v1/escrow/:id/refund  # 退款
```

### 仲裁 API

```
POST /api/v1/arbitrate/submit  # 提交争议
GET  /api/v1/arbitrate/:id     # 查询状态
POST /api/v1/arbitrate/:id/resolve # 仲裁结果
```

---

## 架构

```
┌─────────────────────────────────────┐
│         Agent 平台层                │
│   (ClawIntelligence, OptimAI...)    │
├─────────────────────────────────────┤
│         信任基础设施层              │
│   ┌─────────┬─────────┬─────────┐   │
│   │ 信誉层  │ 托管层  │ 仲裁层  │   │
│   │ (SACRED)│ (Escrow)│(Arbitra)│   │
│   └─────────┴─────────┴─────────┘   │
│          CryptoMinds                │
├─────────────────────────────────────┤
│         支付协议层                  │
│         (x402, APP)                 │
├─────────────────────────────────────┤
│         区块链层                    │
│         (BSC, ETH, SOL)             │
└─────────────────────────────────────┘
```

---

## 项目结构

```
cryptominds/
├── src/
│   ├── credit/          # SACRED 信用分
│   ├── escrow/          # 托管层
│   ├── reputation/      # 信誉层
│   ├── settlement/      # 多链结算
│   ├── verification/    # 验证门
│   └── api/             # API 入口
├── sdk/
│   ├── python/          # Python SDK
│   └── javascript/      # JavaScript SDK
├── tests/               # 测试
├── docs/                # 文档
└── archive/             # 归档
```

---

## 对标 BNB Chain Wishlist

| Wishlist 需求 | CryptoMinds | 状态 |
|---|---|---|
| AI reputation and registration systems | SACRED 五维信用分 | ✅ |
| AI-native payment solutions | 信用分驱动 Escrow 托管 | ✅ |
| Safe autonomous trading agents | Escrow 状态机 + 仲裁 | ✅ |
| Risk Scoring Frameworks | 标准化信用等级 | ✅ |

---

## 开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 API 服务
python src/api_server.py

# 运行测试
pytest tests/
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [白皮书](docs/WHITEPAPER.md) | 产品定位 + 市场分析 |
| [技术规范](docs/WHITEPAPER_TECH_SPEC.md) | 架构 + 状态机 + 安全模型 |
| [API 文档](docs/API.md) | 端点说明 + 示例 |

---

## License

MIT
