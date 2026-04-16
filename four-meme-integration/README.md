# Four.meme × CryptoMinds 接入指南

## 概述

本指南帮助 Four.meme 工程师快速将平台项目接入 CryptoMinds AI Agent 经济体系。通过集成，Four.meme 项目可以获得：

1. **自动化风控分析** - CryptoMinds 专家 Agent 自动扫描合约安全、代币经济学、社区健康度
2. **实时市场监控** - 24/7 监控项目关键指标，异常及时预警
3. **AI 驱动的投资建议** - 基于链上数据和社区情绪，生成投资分析报告
4. **去中心化支付** - 通过 x402 协议实现 Agent 间自动支付结算

## 架构概览

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Four.meme     │    │  CryptoMinds    │    │   BSC/Base/     │
│    Platform     │◄──►│   Orchestrator  │◄──►│    Solana       │
│                 │    │                 │    │     Chains      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Project Registry│    │  Expert Agents  │    │  x402 Payments  │
│      API        │    │  (Scan/Risk/    │    │   Settlement    │
│                 │    │   Analysis)     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 快速开始

### 1. 项目注册

Four.meme 在新项目上线时，调用 CryptoMinds 注册 API：

```javascript
// 示例：注册新项目到 CryptoMinds
const response = await fetch('https://api.cryptominds.ai/v1/projects/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    projectAddress: '0x...',
    name: 'DogWifHat',
    symbol: 'WIF',
    chain: 'bsc',
    creator: '0x...',
    metadata: {
      website: 'https://dogwifhat.com',
      twitter: 'https://twitter.com/dogwifhat',
      telegram: 'https://t.me/dogwifhat'
    }
  })
});
```

### 2. 请求分析

项目方可随时请求分析，或设置自动分析触发器：

```javascript
// 请求风控分析
const analysis = await fetch('https://api.cryptominds.ai/v1/analysis/request', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    projectAddress: '0x...',
    analysisType: 'risk', // risk, scan, report
    payment: {
      amount: '0.0005', // BNB
      token: 'BNB',
      chain: 'bsc'
    }
  })
});
```

### 3. 接收报告

分析完成后，报告将通过 Webhook 或轮询获取：

```javascript
// Webhook 回调（推荐）
// Four.meme 需要提供一个 endpoint 接收报告
app.post('/webhook/cryptominds', (req, res) => {
  const { projectId, report, score, timestamp } = req.body;
  
  // 更新项目状态
  updateProjectAnalysis(projectId, {
    score,
    reportUrl: report.ipfsUrl,
    analyzedAt: timestamp
  });
  
  res.json({ received: true });
});

// 或者轮询获取
const report = await fetch(`https://api.cryptominds.ai/v1/analysis/${analysisId}`);
```

## 智能合约集成

参考合约 `CryptoMindsAdapter.sol` 展示了如何在链上集成。主要功能：

1. **项目注册** - 链上记录项目信息
2. **费用支付** - 通过 x402 协议支付分析费用
3. **结果上链** - 分析结果和评分记录在链上

### 部署步骤

1. 部署 `CryptoMindsAdapter.sol` 到 BSC/Base/Solana
2. 在 CryptoMinds 平台注册合约地址
3. 配置支付代币和费用参数

## API 参考

### 端点列表

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/v1/projects/register` | 注册新项目 |
| GET | `/v1/projects/{address}` | 获取项目信息 |
| POST | `/v1/analysis/request` | 请求分析 |
| GET | `/v1/analysis/{id}` | 获取分析结果 |
| GET | `/v1/market/trending` | 获取趋势项目 |

### 错误处理

```json
{
  "error": {
    "code": "INSUFFICIENT_PAYMENT",
    "message": "支付金额不足",
    "required": "0.0005",
    "provided": "0.0001"
  }
}
```

## 支付说明

### x402 协议支付

CryptoMinds 使用 x402 协议进行 Agent 间支付。支持：

- **多链支付**：BNB Chain、Base、Solana
- **多代币**：BNB、ETH、SOL、USDC
- **智能路由**：自动选择最优支付路径

### 费用结构

| 服务类型 | 费用 (BNB) | 说明 |
|----------|------------|------|
| 扫链服务 | 0.0005 | 扫描新上线代币 |
| 风控分析 | 0.0003 | 合约安全检查 |
| 深度分析 | 0.0010 | 完整代币经济学分析 |
| 实时监控 | 0.0002/天 | 24小时监控 |

## 安全考虑

### 1. API 密钥管理

```javascript
// 使用环境变量
const CRYPTO_MINDS_API_KEY = process.env.CRYPTO_MINDS_API_KEY;

// 请求头
headers: {
  'Authorization': `Bearer ${CRYPTO_MINDS_API_KEY}`
}
```

### 2. Webhook 验证

```javascript
// 验证 CryptoMinds 签名
const signature = req.headers['x-cryptominds-signature'];
const isValid = verifySignature(req.body, signature, WEBHOOK_SECRET);
```

### 3. 速率限制

- 每个项目每小时最多 10 次分析请求
- 每个 IP 每分钟最多 100 次 API 调用

## 测试

### 1. 沙盒环境

```bash
# 使用沙盒 API
API_URL="https://sandbox.cryptominds.ai"

# 测试项目注册
curl -X POST $API_URL/v1/projects/register \
  -H "Content-Type: application/json" \
  -d '{"projectAddress": "0x...", "name": "TestToken"}'
```

### 2. 测试代币

我们在 BSC 测试网部署了测试代币：

- 测试代币合约：`0x...`
- 测试 BNB 水龙头：`https://testnet.bscscan.com`

## 支持与联系

- **技术支持**：tech@cryptominds.ai
- **文档**：https://docs.cryptominds.ai
- **Discord**：https://discord.gg/cryptominds
- **GitHub**：https://github.com/cryptominds/protocol

## 路线图

### Q2 2026
- [x] 基础集成 API
- [x] BSC 链支持
- [ ] Base 链支持
- [ ] Solana 链支持

### Q3 2026
- [ ] 实时监控仪表板
- [ ] 机器学习风险预测
- [ ] 跨链分析聚合

---

**注意**：本文档和参考合约仅为示例，实际集成需要根据 CryptoMinds 最新 API 文档调整。