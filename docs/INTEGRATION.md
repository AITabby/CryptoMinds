# CryptoMinds — Four.meme 集成指南

## 3 步接入

### Step 1: 部署 CryptoMinds API

```bash
cd web && npm install && node server.js
```

配置环境变量：
- `BSC_RPC` — BSC RPC 节点
- `DEPOSIT_POOL_ADDRESS` — Four.meme 质押池地址
- `ADMIN_SECRET` — 管理员密钥

### Step 2: Agent 调用 SDK

```python
from orchestrator import discover_skills, purchase_skill, run_skill

# 发现可用 Skill
skills = discover_skills()

# Agent 自主购买（真实链上支付）
ok, purchase = purchase_skill(
    skill_id="tiedan-scan",
    buyer_wallet="0x...",
    payment_mode="onchain",
    tx_hash="0x..."  # Agent 链上支付后的 tx hash
)

# 执行
result = run_skill("tiedan-scan", "tiedan", "扫描最新 meme 币", buyer_wallet)
```

### Step 3: 配置质押地址

将 `DEPOSIT_POOL_ADDRESS` 设为 Four.meme 提供的质押托管地址。CryptoMinds 不碰钱，只验证质押是否存在。

## 需要适配的项

| 事项 | PoC 现状 | 生产环境 |
|------|---------|---------|
| 支付 | demo 模式 | 真实链上 `txHash` 验证 |
| 质押 | 零地址（跳过验证） | Four.meme 质押池地址 |
| 数据存储 | JSON 文件 | 数据库 |
| Agent Runtime | 本地 Python | 远程调用 / 四。meme 托管 |
| 用户身份 | 钱包地址 | Four.meme 用户系统对接 |

## 不需要改的

- API 接口签名
- x402 支付协议
- 安全扫描逻辑
- 信誉系统
- 智能路由

## 适配器合约

`four-meme-integration/CryptoMindsAdapter.sol` 提供链上适配，Four.meme 可直接集成。

```solidity
// Four.meme 调用示例
adapter.registerExpert{value: deposit}("my-agent", skillId);
adapter.reportViolation(expertAddress, evidence);
```
