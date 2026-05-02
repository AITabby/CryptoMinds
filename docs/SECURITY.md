# CryptoMinds 安全体系

## 核心原则

**不能确认安全，就拒绝。**

扫描器只输出 `safe` 或 `critical`，不存在 warning。任何疑虑都视为不安全。

## 安全扫描

### 流程

```
提交服务 → 安全扫描 → safe（自动上架）| critical（自动拒绝）
```

### 检测项

| 危险模式 | 等级 | 处理 |
|----------|------|------|
| 读取私钥/密钥/mnemonic | critical | 拒绝 |
| 数据外泄（fetch/axios 发送数据） | critical | 拒绝 |
| 签名/加密操作 | critical | 拒绝 |
| 网络监听/端口绑定 | critical | 拒绝 |
| 子进程执行（child_process/exec/spawn） | critical | 拒绝 |
| 环境变量访问（process.env/os.environ） | critical | 拒绝 |
| 动态代码执行（eval/Function/execSync） | critical | 拒绝 |
| 文件写入（writeFile/appendFile） | critical | 拒绝 |
| 敏感路径读取（/etc/passwd, ~/.ssh） | critical | 拒绝 |
| 请求非白名单域名 | critical | 拒绝 |

### 白名单域名

binance.org, bscscan.com, basescan.org, four.meme, dexscreener.com, coingecko.com, geckoterminal.com, dex.guru, etherscan.io, bsc-dataseed, mainnet.base.org

### CLI 使用

```bash
node security/scanner.js <seller-config>
```

## SSRF 防护

卖家注册时提供的 API endpoint 经过完整校验：

1. 只允许 http/https 协议
2. 禁止 localhost / .localhost
3. 禁止内网 IP（10.x / 172.16-31.x / 192.168.x / 127.x）
4. IPv6 也拦（:: / ::1 / fc/fd/fe80）
5. **DNS 解析校验**：域名 lookup 后解析到私网 IP 也拦截
6. `/api/agent-buy` 调用前二次校验 endpoint

## 支付安全

- 购买接口必须提供 `txHash`（链上支付）或显式 `paymentMode: "demo"`
- `txHash` 防重复使用
- 智能路由自动选择最优支付路径

## 质押罚没

- 卖家注册需质押 BNB
- 押金池地址由质押方提供（CryptoMinds 不碰钱）
- 退出时平台只标记 `refundStatus: 'pending'`，退款由质押方处理
- 违规多签确认后罚没，赔偿买方
- 合约：`contracts/SkillStaking.sol`

## 退出市场

- 使用自定义弹窗确认（非浏览器原生 confirm）
- 退出后服务下架
- 押金退还由质押方处理，平台不碰钱

## API 代理安全

Express Gateway (`3457`) 到 Python Flask (`3458`) 的代理遵循以下安全策略：

- **GET (只读)** 端点注入 `X-CryptoMinds-Internal-Token`，浏览器可直接调用
- **POST (写入)** 端点**不注入** internal token，需用户认证：
  - Escrow create/resolve: 需要 `X-Admin-Secret`
  - Session Key revoke/increase-quota: 需要 main_wallet 匹配验证
  - 其他写入: 需要 buyer 签名或 internal token（由客户端显式提供）
- 浏览器不能通过前端代理绕过 Python 的 `@require_auth`

## Escrow 争议仲裁安全

- 仲裁端点 (`/escrow/:id>/resolve`) 需要 `X-Admin-Secret` header
- Admin secret 通过 timing-safe 比较，防止时序攻击
- Demo 模式下 Session Key 操作跳过 ECDSA 签名，用钱包地址匹配验证
- 主私钥不应从浏览器/HTTP 请求体传递（仅 Demo 模式允许占位符）
