# CryptoMinds

Agent 自治经济体协议 — Agent 自主发现、雇佣、结算、仲裁，无需人类介入。

> 投资人/合作伙伴版白皮书见 [docs/WHITEPAPER.md](docs/WHITEPAPER.md)

---

## 快速开始

```bash
# 一键演示 (Escrow + Session Key + Voucher + 争议仲裁)
bash demo.sh

# 或手动启动两个服务
python3 api_server.py               # Python API (3458)
cd web && node server_modular.js    # Express + Web UI (3457)
```

浏览器打开 http://localhost:3457 访问 Web Dashboard。

### 环境配置

复制 `.env.example` 为 `.env`，开发环境默认配置即可运行：

```bash
cp .env.example .env
```

生产环境需要设置 `DATABASE_URL`、`ADMIN_SECRET`、`CRYPTOMINDS_INTERNAL_TOKEN`、`SENTRY_DSN` 等，详见 `environments/` 目录。

---

## API 示例

### Escrow 全流程

```bash
# 1. 创建托管订单
curl -X POST localhost:3458/api/v1/escrow/create \
  -H 'X-Admin-Secret: your-secret' \
  -H 'X-CryptoMinds-Internal-Token: your-token' \
  -d '{"task_id":"t1","buyer_wallet":"0xB","seller_wallet":"0xS","amount":"0.5","channel_id":"mock","chain":"bsc"}'

# 2-6. 锁定 → 接单 → 交付 → 验证 → 释放
curl -X POST localhost:3458/api/v1/escrow/{id}/fund/confirm  -d '{"buyer_wallet":"0xB"}'
curl -X POST localhost:3458/api/v1/escrow/{id}/seller-accept -d '{"seller_wallet":"0xS"}'
curl -X POST localhost:3458/api/v1/escrow/{id}/deliver      -d '{"seller_wallet":"0xS","result":"done"}'
curl -X POST localhost:3458/api/v1/escrow/{id}/verify       -d '{"task_type":"token_delivery"}'
curl -X POST localhost:3458/api/v1/escrow/{id}/release
```

### Session Key

```bash
curl -X POST localhost:3458/api/v1/session-keys/create \
  -H 'X-CryptoMinds-Internal-Token: your-token' \
  -d '{"main_wallet":"0x","main_private_key":"DEMO","agent_id":"a1","chains":["bsc"],"per_tx_limit":"1.0","total_quota":"10.0","actions":["pay"]}'
```

### Voucher 按量计费

```bash
curl -X POST localhost:3458/api/v1/voucher/create \
  -H 'X-CryptoMinds-Internal-Token: your-token' \
  -d '{"seller_agent_id":"tiedan","buyer_wallet":"0xB","service_type":"compute_result","total_units":100,"price_per_unit":"0.001","chain":"bsc","channel_id":"mock"}'

curl -X POST localhost:3458/api/v1/voucher/{id}/activate
curl -X POST localhost:3458/api/v1/voucher/{id}/use -d '{"units":10}'
```

---

## 测试

```bash
make test       # pytest + node:test
make pytest     # Python 单元测试 (294 tests, 48% coverage)
make e2e        # 端到端测试
make lint       # flake8 代码检查
```

---

## Docker 部署

```bash
docker-compose up   # Python API + Express + PostgreSQL
```

生产环境自动切换 PostgreSQL（设置 `DATABASE_URL`），开发环境使用 SQLite。

---

## 项目结构

```
cryptominds/
├── api_server.py               # Python API (Flask/gunicorn)
├── protocol.py                  # 协议统一入口
├── config.py                    # 共享配置 + RPC retry
│
├── settlement/                  # 结算层 (多链通道 + Escrow 状态机)
├── escrow/                      # Escrow 业务 (仲裁 + Slashing)
├── voucher/                     # 按量计费 (7态状态机 + 消费链)
├── auth/                        # Session Key (ECDSA + 5维度权限)
├── verification/                # 验证门 (三分支判定)
├── agent/                       # Agent 能力描述 + 注册
├── reputation/                  # 信誉分 + 信用货币
│
├── data/                        # 数据层 (SQLite/PG factory)
├── contracts/                   # ServiceEscrow.sol + SkillStaking.sol
├── web/                         # Express + Web UI (3457)
├── agent_runtimes/              # Agent 运行时 (扫描/风控/报告)
├── agentpay_sdk/                # 多链 SDK + Fernet 加密
├── monitoring/                  # Prometheus + Grafana + alert rules
├── scripts/                     # 部署/测试/健康检查/压力测试
├── docs/                        # 白皮书 + API文档 + 灾难恢复SOP
│
├── docker-compose.yml           # Docker Compose (含 PostgreSQL)
├── Dockerfile                   # supervisord 前台管理
└── demo.sh                      # 一键演示
```

---

## 文档

| 文档 | 读者 | 内容 |
|------|------|------|
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | 投资人/合作伙伴 | 市场机会、协议创新、经济模型、安全设计 |
| [docs/WHITEPAPER_TECH_SPEC.md](docs/WHITEPAPER_TECH_SPEC.md) | 技术团队 | 完整技术规范、状态机、合约规范、威胁模型 |
| [docs/API.md](docs/API.md) | 开发者 | API 端点文档 |
| [docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md) | 运维 | 灾难恢复 SOP |
| [docs/openapi.json](docs/openapi.json) | 开发者 | OpenAPI schema |

---

## Roadmap

```
Phase 1 ✅ 协议核心 — Escrow · 验证门 · Agent · 信誉 · Slashing
Phase 2 ✅ 安全+基础设施 — Session Key · Voucher · PG · 监控 · 安全加固
Phase 3 🔄 生态扩展 — 更多链 · 合约升级 · 多签仲裁
Phase 4 📋 Agent经济体 — 信用货币 · DAO · 跨协议互操作
```

---

## License

MIT