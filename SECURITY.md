# Security Policy

## 报告漏洞

如果你发现了安全漏洞，请**不要**公开提交 Issue。通过以下方式私下报告：

- 发送邮件至项目维护者
- 在报告中包含：漏洞描述、复现步骤、影响范围

我们会在 48 小时内响应，7 天内提供修复或缓解方案。

## 安全措施

### 密钥与凭证

- **钱包加密**：wallets.json 使用 Fernet 对称加密（`WALLET_ENCRYPTION_KEY` 环境变量），私钥不以明文存储
- **Admin 验证**：使用 `hmac.compare_digest` 时序安全比较，防止 timing attack
- **HMAC 回退禁止**：`eth_account` 缺失时生产环境直接 crash，不降级到不安全的 HMAC 验证
- **Demo 私钥过滤**：生产环境拒绝 `DEMO`、`PLACEHOLDER`、`TEST` 等占位私钥

### API 安全

- **Rate Limiting**：Express `express-rate-limit` + Flask `Flask-Limiter`，信用货币发行限制 5/min
- **CORS**：`ALLOWED_ORIGINS` 白名单，Express 和 Flask 双层配置
- **Internal Token**：服务间通信通过 `X-Internal-Token` 头验证
- **Agent 签名**：链上 ECDSA 签名验证（EIP-191），支持 MetaMask 签名恢复

### 合约安全

- **Escrow 状态机**：11 态严格转换，非法状态转换会被 revert
- **仲裁时间锁**：`MINIMUM_ARBITRATION_WAIT_SECONDS`（5 分钟），防止闪电仲裁
- **Seller Slashing**：恶意行为自动惩罚，信誉加权仲裁
- **超时保护**：买家确认超时自动放款，卖家交付超时自动退款，无需人工干预

### 基础设施

- **HTTPS**：`SSL_CERT_PATH` + `SSL_KEY_PATH` 自动切换
- **Docker**：supervisord 前台进程管理 + 自动重启
- **RPC 安全**：`create_web3_with_retry()` 支持 timeout/retry/fallback，防止 RPC 挂起
- **Sentry**：`SENTRY_DSN` 错误上报，生产环境实时监控
- **Prometheus**：14 counter + 2 gauge，全端点监控
- **数据库备份**：定期 SQLite WAL checkpoint + 10 份轮转

### 信用分模块

- **独立数据库**：`credit_score.db` 与主库 `cryptominds.db` 物理隔离
- **快照哈希**：每次计算结果生成 SHA-256 哈希，防篡改
- **查询授权**：第三方查询需 Agent 签名授权，支持链上签名验证
- **只读桥接**：`CreditScoreBridge` 只从主库读取，不写入，不修改

### 审计与测试

- 292 个 pytest 用例 + 8 个 Node 测试
- 覆盖率 48%，核心状态机覆盖 >80%
- CI/CD：lint + pytest + node-test + docker-build 四阶段

## 生产部署检查清单

- [ ] `WALLET_ENCRYPTION_KEY` 已设置
- [ ] `ADMIN_SECRET` 使用强随机值
- [ ] `CRYPTOMINDS_INTERNAL_TOKEN` 使用强随机值
- [ ] `DEMO_MODE=false`
- [ ] `CRYPTOMINDS_DEBUG=false`
- [ ] HTTPS 已启用
- [ ] CORS 白名单已配置
- [ ] Rate Limiting 已启用
- [ ] Python API / PostgreSQL 端口不暴露公网
- [ ] Sentry DSN 已配置
