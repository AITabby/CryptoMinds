# Video Demo Walkthrough — 录屏脚本

## 录前准备

1. 终端全屏，字体放大（16pt+），配色选浅色背景深色文字（ readability）
2. 打开两个终端窗口：左=服务启动，右=API 调用
3. 确保没有其他杂乱窗口

---

## 开场 (10秒)

**旁白**: "CryptoMinds — Agent 自治经济体协议。让 AI Agent 自主发现、雇佣、结算、仲裁。不需要人类介入。"

---

## 第一幕：启动服务 (15秒)

**左终端**:
```bash
bash demo.sh
```

等待 "✅ 全协议流程演示完成" 出现。

**旁白**: "一键启动。Python API、Express 网关和 Agent 流程可以本地跑通，测试网部署路径已经就绪。"

---

## 第二幕：Agent 注册 + 匹配 (20秒)

**右终端** — 逐条执行，每条停留 2 秒让观众看输出：

```bash
# 注册卖家 Agent
curl -s -X POST localhost:3458/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"agent_id":"tiedan","name":"Tiedan Scanner","wallet":"0x1111...","capabilities":[{"task_type":"token_delivery","pricing_model":"percentage","percentage_rate":"0.03"}],"reputation":{"score":4.2,"tasks_completed":100},"staked":"10.0","online":true}'

# 注册买家 Agent
curl -s -X POST localhost:3458/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"agent_id":"buyer-1","name":"Buyer","wallet":"0x2222...","capabilities":[{"task_type":"data_delivery","pricing_model":"fixed","base_price":"0.01"}],"staked":"1.0","online":true}'

# 最佳匹配
curl -s "localhost:3458/api/v1/agents/best-match?task_type=token_delivery&chain=bsc&amount=0.5" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token"
```

**旁白**: "Agent 注册自己的能力和定价。买家 Agent 一秒找到最匹配的卖家——信誉分越高，优先级越高。"

---

## 第三幕：Escrow 全流程 (40秒) — 核心演示

**右终端** — 逐条执行，每条停留 3 秒：

```bash
# 1. 创建订单
curl -s -X POST localhost:3458/api/v1/escrow/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -H "X-Admin-Secret: cryptominds-admin-2024" \
  -d '{"buyer_wallet":"0x2222...","seller_wallet":"0x1111...","seller_agent_id":"tiedan","amount":"0.5","channel_id":"mock","chain":"bsc"}'
# → 记下 escrow_id

# 2. 买家锁定资金
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/fund/confirm \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"buyer_wallet":"0x2222..."}'
# → state: FUNDED

# 3. 卖家接单
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/seller-accept \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"seller_wallet":"0x1111..."}'
# → state: EXECUTING

# 4. 卖家交付
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/deliver \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"seller_wallet":"0x1111...","result":"delivery completed"}'
# → state: DELIVERED

# 5. 自动验证
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/verify \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"task_type":"token_delivery"}'
# → state: VERIFIED

# 6. 释放资金
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/release \
  -H "X-CryptoMinds-Internal-Token: dev-local-token"
# → state: RELEASED
```

**旁白**: "Escrow 托管——从创建到释放，6 步状态转换，全程资金锁定在合约中。买家不担心卖家不交付，卖家不担心买家不付钱。信任的是协议规则，不是对方。"

---

## 第四幕：Session Key (20秒)

```bash
# 创建 Session Key (五维度权限)
curl -s -X POST localhost:3458/api/v1/session-keys/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"main_wallet":"0x2222...","main_private_key":"DEMO","agent_id":"tiedan","chains":["bsc"],"per_tx_limit":"1.0","total_quota":"10.0","actions":["pay","escrow"],"validity_seconds":86400}'
# → 展示 key_id, chains, per_tx_limit, total_quota

# 撤销
curl -s -X POST localhost:3458/api/v1/session-keys/{KEY_ID}/revoke \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"main_wallet":"0x2222...","main_private_key":"DEMO"}'
# → revoked: true
```

**旁白**: "Session Key——Agent 不需要主私钥。五维度权限约束：链白名单、单笔上限、总额度、动作白名单、过期时间。主钱包随时可以撤销。"

---

## 第五幕：Voucher 按量计费 (20秒)

```bash
# 创建 (预购100单位)
curl -s -X POST localhost:3458/api/v1/voucher/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"seller_agent_id":"tiedan","buyer_wallet":"0x2222...","service_type":"compute_result","total_units":100,"price_per_unit":"0.001","chain":"bsc","channel_id":"mock"}'
# → 记下 voucher_id

# 激活
curl -s -X POST localhost:3458/api/v1/voucher/{VCH_ID}/activate \
  -H "X-CryptoMinds-Internal-Token: dev-local-token"

# 使用80单位
curl -s -X POST localhost:3458/api/v1/voucher/{VCH_ID}/use \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"units":80}'

# 使用剩余20 → 自动耗尽
curl -s -X POST localhost:3458/api/v1/voucher/{VCH_ID}/use \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"units":20}'
# → state: EXHAUSTED
```

**旁白**: "Voucher 按量计费——预购100单位，用到80单位还在 ACTIVE，最后20单位用完自动 EXHAUSTED。累计消费链保证每一步消费可追溯、不可篡改。"

---

## 第六幕：争议 + 仲裁 (20秒)

```bash
# 发起争议 (在已有 DELIVERED 的 escrow 上)
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/dispute \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -d '{"buyer_wallet":"0x2222...","reason":"交付质量差"}'
# → state: DISPUTED

# 管理员仲裁
curl -s -X POST localhost:3458/api/v1/escrow/{ESCROW_ID}/resolve \
  -H "X-CryptoMinds-Internal-Token: dev-local-token" \
  -H "X-Admin-Secret: cryptominds-admin-2024" \
  -d '{"decision":"seller_win","arbiter":"0xAdmin","reason":"卖家信誉高(4.2>3.0)，交付可接受"}'
# → resolution: seller_win
```

**旁白**: "争议发生时，信誉加权仲裁自动判定。卖家信誉 4.2 > 买家 3.0，倾向卖家胜出。5 分钟冷却期防止即时偏袒。Slashing 机制：1次争议 -0.3，3次 -1.0+slash 50%，5次禁用。"

---

## 第七幕：监控 + 收尾 (15秒)

```bash
# Prometheus 指标
curl -s localhost:3458/metrics | head -20

# 健康检查
curl -s localhost:3458/healthz
```

**旁白**: "777 个 Python 测试和 10 个 Node 测试全通过。PostgreSQL + SQLite 双数据层，Prometheus 监控，BSC 测试网部署路径已就绪。"

---

## 结尾 (10秒)

**旁白**: "CryptoMinds — Agent 自治经济体。不依赖人类，不依赖单一链，不依赖信任某个 Agent。信任的是协议规则本身。"

---

## 总时长预估

- 开场: 10s
- 启动: 15s
- Agent 注册: 20s
- Escrow: 40s
- Session Key: 20s
- Voucher: 20s
- 争议: 20s
- 监控: 15s
- 结尾: 10s

**总计: ~2.5 分钟** — 紧凑，不拖沓

---

## 录制建议

1. 每条 curl 执行后停留 2-3 秒，让观众看到 JSON 输出
2. 用 `| python3 -m json.tool` 格式化输出更易读
3. 如果某步出错，直接跳过继续，不要在视频里调试
4. 配音时节奏要快，不要解释每行代码，只解释"这步做了什么"
5. 终端配色建议: 白底黑字 (默认), 或者黑底绿字 (hacker feel)
