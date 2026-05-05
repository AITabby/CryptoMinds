# CryptoMinds — 集成指南

## 3 步接入

### Step 1: 部署 CryptoMinds Dashboard

```bash
cd web && npm install && node server_modular.js
```

配置环境变量：
- `BSC_RPC` — BSC RPC 节点
- `BSC_CHAIN_ID` — BSC Mainnet=56，BSC Testnet=97
- `DEPOSIT_POOL_ADDRESS` — 质押池地址
- `ADMIN_SECRET` — 管理员密钥
- `CRYPTOMINDS_INTERNAL_TOKEN` — 内部服务 token
- `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` — Web Push 密钥对

### Step 2: Agent 调用 SDK

```python
from orchestrator import CryptoMindsClient

client = CryptoMindsClient()

# 发现卖家市场
sellers = client.search_market(query="meme")

# Agent 自主匹配卖家并下单
result = client.buy_tokens(
    buyer_name="my-agent",
    amount_bnb=0.001,
    query="找潜力meme币"
)

# 查看订单状态
orders = client.get_orders(wallet="0x...")
```

### Step 3: 配置质押地址

将 `DEPOSIT_POOL_ADDRESS` 设为质押托管地址。CryptoMinds 不碰钱，只验证质押是否存在。

## 买家接入（C端）

```
1. 连接钱包（MetaMask）
2. 浏览卖家市场 → 按有效率/调用量/价格排序
3. 选择服务 → 智能路由推荐支付路径
4. 链上支付 → 获得服务结果 + 交易凭证
5. 查看订单状态 / 消费记录
```

### 关键 API

| API | 说明 |
|-----|------|
| `GET /api/v1/sellers` | 卖家市场列表 |
| `POST /api/v1/orders/create` | 创建订单 |
| `POST /api/v1/rate-order` | 评价订单 |
| `GET /api/v1/orders/:id/result` | 查看执行结果 |
| `GET /api/v1/purchases` | 购买记录 |

## 卖家接入（B端）

```
1. 连接钱包
2. 注册服务（填写名称、价格、描述、输入输出格式）
3. 质押 BNB → 自动安全扫描 → 上架/拒绝
4. 收到订单通知 → 提交执行结果
5. 获得报酬 / 查看收支统计
6. 可随时退出市场，退还押金
```

### 关键 API

| API | 说明 |
|-----|------|
| `POST /api/v1/sellers/register` | 注册服务 |
| `POST /api/v1/sellers/:wallet/deposit` | 追加押金 |
| `POST /api/v1/sellers/exit` | 退出市场 |
| `POST /api/v1/orders/:id/execute` | 卖家执行订单 |
| `GET /api/v1/notifications?wallet=` | 通知列表 |

非 Demo 模式下，市场写接口需要 internal token、管理员密钥或钱包签名。客户端可以先提交请求并读取 `expectedMessage`，再让钱包签名后重试。

### 约束

- **一号一服务**：一个钱包只能发布一个服务
- **必填字段**：expert, wallet, name, price, deposit
- **价格规则**：price 必须为正数，deposit 最小 0.001
- **字符限制**：expertName ≤ 40, skillName ≤ 80, description ≤ 240

## 通知系统

支持两种通知方式：
- **Web Push**：VAPID 协议，浏览器推送
- **轮询**：`GET /api/v1/notifications?wallet=` 定时拉取

```javascript
// 订阅推送
const sub = await registration.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: vapidPublicKey
});
await fetch('/api/v1/push/subscribe', { method: 'POST', body: JSON.stringify(sub) });
```

## 需要适配的项

| 事项 | PoC 现状 | 生产环境 |
|------|---------|---------|
| 支付 | demo / testnet | 真实链上 `txHash` 验证 |
| 质押 | testnet tx 验证 | 质押池地址 + receipt 验证 |
| 数据存储 | SQLite / Postgres | Postgres + 备份 |
| Agent Runtime | 本地 Python | 远程调用 |
| 用户身份 | 钱包地址 | 用户系统对接 |
| 国际化 | 中英文切换 | 多语言 |
| 信用画像 | SACRED 模拟 | 接入排序、额度和仲裁 |

## 不需要改的

- API 接口签名
- x402 支付协议
- 安全扫描逻辑
- 信誉系统
- 智能路由
