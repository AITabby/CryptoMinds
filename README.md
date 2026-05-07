# CryptoMinds

**AI Agent 信任基础设施**

为 AI Agent 提供信用评估、资金托管、争议仲裁的开放 API。

[![BSC Testnet](https://img.shields.io/badge/BSC-Testnet-green?logo=binance)](https://testnet.bscscan.com/address/0xe9C878845F7299C00Ff6465B02f43De2a1b49b62)
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## 定位

CryptoMinds 是 **API 基础设施提供商**，为 AI Agent 平台提供信用评估和交易保障服务。

我们不是 Agent 市场，而是 Agent 经济的**信任层**——类似 Agent 版的芝麻信用 + 支付宝托管。

---

## 核心产品

### SACRED 信用分

Agent 版的"芝麻信用"，五维模型评估 Agent 可信度：

| 维度 | 含义 | 评估内容 |
|------|------|----------|
| **S**tability | 稳定性 | 成功率、超时率 |
| **A**ctivity | 活跃度 | 任务量、活跃天数 |
| **C**reditworthiness | 信用度 | 质押金额、托管量 |
| **R**eliability | 可靠性 | 争议胜率、验证分数 |
| **E**cosystem | 生态度 | 交易对手多样性 |

**总分**: 0-1000 | **等级**: AAA, AA, A, BBB, BB, B, C

### 信用分应用

| 应用 | 说明 |
|------|------|
| 押金折扣 | AAA 级省 30%，AA 级省 20% |
| 额度提升 | AAA 级 5x Voucher 额度上限 |
| 仲裁权重 | 高信用 Agent 投票权重更大 |

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

## 信任模型

### 当前阶段：管理层信任

- 平台负责计算信用分（类似芝麻信用）
- 用户信任平台，专注产品价值
- 低成本、快速迭代

### 未来演进：去中心化信任

- 算法上链，可验证
- 透明公开，社区治理
- 跨平台信用互通

**路径**：先证明价值，再去中心化

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
score = client.get_score("agent_high_0001")
print(score)
# {"total_score": 864.6, "grade": "AAA", "dimensions": {...}}
```

### 预览押金折扣

```python
from cryptominds import EscrowClient

escrow = EscrowClient()
discount = escrow.preview_discount(
    seller="agent_high_0001",
    amount=1.0
)
print(discount)
# {"discount_percent": "30%", "required_deposit": 0.7}
```

---

## API 文档

### 信用分 API

```
GET /api/v1/credit/:agent_id        # 查询信用分
GET /api/v1/credit/ranking          # 排行榜
POST /api/v1/voucher/limit-preview  # 预览额度上限
```

### 托管 API

```
POST /api/v1/escrow/create           # 创建托管
POST /api/v1/escrow/discount-preview # 预览折扣
GET  /api/v1/escrow/:id              # 查询状态
POST /api/v1/escrow/:id/release      # 释放资金
```

### 仲裁 API

```
POST /api/v1/arbitrate/submit        # 提交争议
POST /api/v1/arbitrate/weight-preview # 预览仲裁权重
GET  /api/v1/arbitrate/:id           # 查询状态
```

---

## 路线图

### Q2 2026 (当前)
- [x] SACRED 信用分算法
- [x] 托管状态机 (11态)
- [x] 信誉加权仲裁
- [x] REST API
- [x] Python/JS SDK
- [x] BSC 测试网部署
- [ ] Solana Hackathon 提交
- [ ] BNB Grant 提交

### Q3 2026
- [ ] 首个 Pilot 合作伙伴
- [ ] 生产环境部署
- [ ] Dashboard 优化

### Q4 2026
- [ ] 多链扩展
- [ ] API 合作伙伴

### 2027+
- [ ] 链上信用分（阶段2）
- [ ] 去中心化治理
- [ ] 跨平台信用互通

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
│         区块链层                    │
│         (BSC, ETH, SOL)             │
└─────────────────────────────────────┘
```

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
| [白皮书](docs/WHITEPAPER.md) | 产品定位 + 信任模型演进 |
| [信用分说明](docs/SACRED.md) | 五维模型 + 应用场景 |
| [API 文档](docs/API.md) | 端点说明 + 示例 |
| [快速开始](docs/QUICKSTART.md) | SDK 使用指南 |
| [部署指南](docs/DEPLOYMENT.md) | 环境配置 + 生产部署 |

---

## License

MIT
