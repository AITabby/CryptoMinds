# Changelog

## 2026-05-03 — 主网部署加固 + 测试基线更新

- **主网部署路径加固**：Nginx/SSL 反代、Docker 内部端口隔离、生产环境显式 `CRYPTOMINDS_ENV=prod` 与 `DEMO_MODE=false`
- **链上/本地状态一致性**：BSC Escrow release 与 dispute resolve 均改为链上确认成功后再落本地终态
- **签名授权收口**：Session Key 生产路径改为主钱包签名授权，禁止主私钥进入后端；Voucher 写路径要求钱包签名
- **测试基线**：`635 passed, 1 skipped` pytest，全量覆盖率 `70.75%`（达到 70% 门槛）；Node `10 passed`

## 2026-05-01 — Escrow 争议 + Session Key 授权 + 安全加固

- **Escrow 状态机**：11 状态完整生命周期 (created → funded → executing → delivered → verified → released, 含争议/仲裁/超时分支)
- **验证门三分支**：pass+阈值 → 自动 release, pass+低分 → DISPUTED, fail → DISPUTED
- **信誉加权仲裁**：buyer_weight = buyer_rep/(buyer_rep+seller_rep), 自动超时高信誉方胜出
- **Seller slashing**：1 buyer_win → -0.3 rep, 3 次/7天 → -1.0 + 50% stake slash, 5+ → 禁用
- **Session Key 授权**：派生 ECDSA 密钥对 + 主钱包 ECDSA 签名授权, 权限约束 (chain/per_tx_limit/total_quota/callable_actions/expiry/nonce)
- **API 端点**：Escrow 5 个 + Session Key 5 个 (Flask + Express 双端口)
- **Express 安全加固**：GET 注入 internal token, POST 不注入需用户认证, admin 操作 requireAdmin + 转发 X-Admin-Secret
- **Demo 模式**：Session Key 创建/撤销/提额 支持 DEMO 占位符私钥
- **OpenAPI 3.0.0**：新增 Escrow/Session Key schema 和 admin_secret security scheme
- **前端新增两个 tab**：争议仲裁 + Session Key 管理
- **Node.js 数据层**：新增 escrow_orders/session_keys 表 + _migrate() 自动补列
- **635 pytest passing, 1 skipped**（当前总覆盖率 70.75%，Node 10 tests passing）

## 2026-04-18 — 智能合约上线 + 清理优化

- **部署 ServiceEscrow 合约** (`0x47e19043...`) — BSC 主网担保交易
- **部署 SkillStaking 合约** (`0x287A44aA...`) — BSC 主网质押罚没
- **完成 Escrow 全流程验证** — createOrder → deliver → confirm，链上成功
- **前端优化**：刷新保持当前页、买家/卖家指标分离、消费记录表格化
- **后端优化**：新增 /api/balance、/api/my-orders、/api/received-orders、/api/seller-stats
- **Escrow 支付验证兼容**：支持合约地址作为 tx.to
- **质押地址改为 SkillStaking 合约**
- **代码清理**：删除 7 个未使用 API、6 个未使用前端函数，减少 300+ 行

## 2026-04-17 — 商业模式升级

- 核心转变：从卖 Skill（工具）→ 卖服务（结果）
- Agent 经济闭环：人类发任务+赏金 → agent 接单赚BNB → 能力不够买服务 → 循环
- 质押机制设计：押金锁合约，退款率超阈值自动罚没
- 有效率闭环：任务执行副产物自动标记有效/无效，信号上链

## 2026-04-14 — 评审优化

- 新增 `scripts/run_poc.sh` 一键启动脚本
- 新增 `scripts/health_check.py` 健康检查（钱包 / Web / BSC RPC）
- 新增 `scripts/env_loader.py` 环境变量加载与校验
- 新增 `.env.example` 配置模板
- README 增加"评审验证"和"集成到 Four.meme"章节

## 2026-04-10 — x402 支付集成

- 集成 HTTP x402 支付协议，支持按次链上结算
- 交易哈希 BSCScan 可查
- 支付验证 + 降级转账双通道

## 2026-04-07 — 多 Agent 协作

- 调度器支持多 Agent 分工（扫链 / 风控 / 报告）
- Agent 间 HTTP 调用 + 本地降级
- 声誉系统上线
