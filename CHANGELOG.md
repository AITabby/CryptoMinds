# Changelog

## 2026-04-14 — 评审优化

- 新增 `scripts/run_poc.sh` 一键启动脚本
- 新增 `scripts/health_check.py` 健康检查（钱包 / Web / BSC RPC）
- 新增 `scripts/env_loader.py` 环境变量加载与校验
- 新增 `.env.example` 配置模板
- README 增加"评审验证"和"集成到 Four.meme"章节
- 整理项目结构：scripts/、tests/、docs/ 分类归档

## 2026-04-10 — x402 支付集成

- 集成 HTTP x402 支付协议，支持按次链上结算
- 交易哈希 BSCScan 可查
- 支付验证 + 降级转账双通道

## 2026-04-07 — 多 Agent 协作

- 调度器支持多 Agent 分工（扫链 / 风控 / 报告）
- Agent 间 HTTP 调用 + 本地降级
- 声誉系统上线
