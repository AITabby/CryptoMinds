# Changelog

## 2026-04-18 — 智能合约上线 + 清理优化

- **部署 ServiceEscrow 合约** (`0x1A81a18d...`) — BSC 主网担保交易
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
