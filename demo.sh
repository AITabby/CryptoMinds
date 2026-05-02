#!/bin/bash
# CryptoMinds 一键演示脚本
# 启动服务 + 自动演示全协议流程 (Escrow + Session Key + Voucher + 争议)

set -e
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

API_PORT=3458
# Load credentials from environments/.env.dev or .env, with fallback defaults
INTERNAL_TOKEN="dev-local-token"
ADMIN_SECRET="cryptominds-admin-2024"
if [ -f "environments/.env.dev" ]; then
    _tok=$(grep CRYPTOMINDS_INTERNAL_TOKEN environments/.env.dev | cut -d= -f2)
    [ -n "$_tok" ] && INTERNAL_TOKEN="$_tok"
fi
if [ -f ".env" ]; then
    _sec=$(grep ADMIN_SECRET .env | cut -d= -f2)
    [ -n "$_sec" ] && ADMIN_SECRET="$_sec"
fi

echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   CryptoMinds — 全协议流程演示         ║${NC}"
echo -e "${CYAN}║   Escrow · Session Key · Voucher       ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: 启动服务 ──────────────────────────────────

echo -e "${YELLOW}[1/6]${NC} 清理旧进程..."
pkill -f "api_server.py" 2>/dev/null || true
pkill -f "server_modular.js" 2>/dev/null || true
sleep 1

echo -e "${YELLOW}[2/6]${NC} 启动 Python API (端口 $API_PORT)..."
export CRYPTOMINDS_DEBUG=true
export DEMO_MODE=true
export ADMIN_SECRET="$ADMIN_SECRET"
export CRYPTOMINDS_INTERNAL_TOKEN="$INTERNAL_TOKEN"
python3 api_server.py &
sleep 3

if curl -sf http://localhost:$API_PORT/healthz > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Python API 正常"
else
    echo -e "  ${RED}✗${NC} Python API 无响应"
    exit 1
fi

echo -e "${YELLOW}[3/6]${NC} 启动 Express Web Dashboard (端口 3457)..."
node web/server_modular.js &
sleep 3

if curl -sf http://localhost:3457 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Web Dashboard 正常 — http://localhost:3457"
else
    echo -e "  ${RED}✗${NC} Web Dashboard 无响应"
fi

# ── Step 2: Agent 注册 ─────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  DEMO 1: Agent 注册 + 发现${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}→ 注册卖家 Agent (tiedan)${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{
    "agent_id": "tiedan",
    "name": "Tiedan Scanner",
    "description": "链上扫描 Agent",
    "wallet": "0x1111111111111111111111111111111111111111",
    "endpoint": "http://localhost:5001",
    "capabilities": [{"task_type":"token_delivery","verification_gate":"token_delivery","supported_chains":["bsc"],"supported_channels":["bsc-native"],"pricing_model":"percentage","percentage_rate":"0.03","available":true}],
    "reputation": {"score":4.2,"tasks_completed":100,"tasks_failed":5,"total_volume":"50"},
    "staked": "10.0",
    "online": true
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} agent_id={d.get(\"agent_id\",\"?\")}')"

echo -e "${YELLOW}→ 注册买家 Agent${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{
    "agent_id": "buyer-001",
    "name": "Buyer Agent",
    "description": "自主下单 Agent",
    "wallet": "0x2222222222222222222222222222222222222222",
    "endpoint": "http://localhost:5002",
    "capabilities": [{"task_type":"data_delivery","verification_gate":"data_delivery","supported_chains":["bsc"],"supported_channels":["mock"],"pricing_model":"fixed","base_price":"0.01","available":true}],
    "reputation": {"score":3.0,"tasks_completed":10,"tasks_failed":0,"total_volume":"1"},
    "staked": "1.0",
    "online": true
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} agent_id={d.get(\"agent_id\",\"?\")}')"

echo -e "${YELLOW}→ 搜索最佳匹配${NC}"
curl -s "http://localhost:$API_PORT/api/v1/agents/best-match?task_type=token_delivery&chain=bsc&amount=0.5" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" | python3 -c "import sys,json; d=json.load(sys.stdin); a=d.get('agent',{}); print(f'  ✓ 最佳匹配: {a.get(\"name\",\"?\")} (score={a.get(\"reputation\",{}).get(\"score\",\"?\")})')"

# ── Step 3: Escrow 全流程 ──────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  DEMO 2: Escrow 托管全流程${NC}"
echo -e "${BOLD}  create → fund → seller-accept → deliver → verify → release${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}→ 创建 Escrow 订单${NC}"
ESCROW=$(curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -d '{"task_id":"demo-task-1","buyer_wallet":"0x2222222222222222222222222222222222222222","seller_wallet":"0x1111111111111111111111111111111111111111","seller_agent_id":"tiedan","amount":"0.5","channel_id":"mock","chain":"bsc","verification_threshold":0.7}')
ESCROW_ID=$(echo "$ESCROW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('escrow_id',''));")
ESCROW_STATE=$(echo "$ESCROW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',''));")
echo -e "  ${GREEN}✓${NC} escrow_id=$ESCROW_ID, state=$ESCROW_STATE"

echo -e "${YELLOW}→ 买家锁定资金 (fund/confirm)${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$ESCROW_ID/fund/confirm \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"buyer_wallet":"0x2222222222222222222222222222222222222222"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${YELLOW}→ 卖家接单 (seller-accept)${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$ESCROW_ID/seller-accept \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"seller_wallet":"0x1111111111111111111111111111111111111111"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${YELLOW}→ 卖家交付 (deliver)${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$ESCROW_ID/deliver \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"seller_wallet":"0x1111111111111111111111111111111111111111","result":"token delivery completed","evidence":{"tx_hash":"0xabc"}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${YELLOW}→ 验证交付 (verify) — 三分支判定${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$ESCROW_ID/verify \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"task_type":"token_delivery","buyer_wallet":"0x2222222222222222222222222222222222222222","seller_wallet":"0x1111111111111111111111111111111111111111","amount":"0.5"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${YELLOW}→ 释放资金 (release)${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$ESCROW_ID/release \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${GREEN}  ✅ Escrow 全流程完成: CREATED → FUNDED → EXECUTING → DELIVERED → VERIFIED → RELEASED${NC}"

# ── Step 4: Session Key ────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  DEMO 3: Session Key 授权${NC}"
echo -e "${BOLD}  创建 → 权限检查 → 撤销${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}→ 创建 Session Key (五维度权限约束)${NC}"
SK=$(curl -s -X POST http://localhost:$API_PORT/api/v1/session-keys/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"main_wallet":"0x2222222222222222222222222222222222222222","main_private_key":"DEMO","agent_id":"tiedan","chains":["bsc"],"per_tx_limit":"1.0","total_quota":"10.0","actions":["pay","escrow"],"validity_seconds":86400}')
SK_ID=$(echo "$SK" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('key_id',''));")
echo "$SK" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  ✓ key_id={d.get(\"key_id\",\"?\")}, chains={d.get(\"available_chains\",[])}, per_tx_limit={d.get(\"per_tx_limit\",\"?\")}, total_quota={d.get(\"total_quota\",\"?\")}')"

echo -e "${YELLOW}→ 撤销 Session Key${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/session-keys/$SK_ID/revoke \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"main_wallet":"0x2222222222222222222222222222222222222222","main_private_key":"DEMO"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} revoked, nonce={d.get(\"nonce\",\"?\")}')"

# ── Step 5: Voucher 按量计费 ───────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  DEMO 4: Voucher 按量计费${NC}"
echo -e "${BOLD}  创建 → 激活 → 使用 → 耗尽${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}→ 创建 Voucher (预购 100 单位)${NC}"
VCH=$(curl -s -X POST http://localhost:$API_PORT/api/v1/voucher/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"seller_agent_id":"tiedan","buyer_wallet":"0x2222222222222222222222222222222222222222","service_type":"compute_result","total_units":100,"price_per_unit":"0.001","chain":"bsc","channel_id":"mock"}')
VCH_ID=$(echo "$VCH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('voucher_id',''));")
echo "$VCH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  ✓ voucher_id={d.get(\"voucher_id\",\"?\")}, state={d.get(\"state\",\"?\")}, total_units={d.get(\"total_units\",\"?\")}')"

echo -e "${YELLOW}→ 激活 Voucher${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/voucher/$VCH_ID/activate \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}')"

echo -e "${YELLOW}→ 使用 80 单位${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/voucher/$VCH_ID/use \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"units":80,"actor":"buyer"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}, units_used={d.get(\"units_used\",\"?\")}')"

echo -e "${YELLOW}→ 使用剩余 20 单位 → 自动耗尽${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/voucher/$VCH_ID/use \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"units":20,"actor":"buyer"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")}, units_used={d.get(\"units_used\",\"?\")}')"

echo -e "${GREEN}  ✅ Voucher 全流程完成: ISSUED → ACTIVE → EXHAUSTED${NC}"

# ── Step 6: 争议仲裁 ──────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  DEMO 5: 争议 + 仲裁${NC}"
echo -e "${BOLD}  dispute → 5分钟冷却 → resolve${NC}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}→ 创建争议 Escrow${NC}"
DISPUTE=$(curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -d '{"task_id":"demo-dispute","buyer_wallet":"0x2222222222222222222222222222222222222222","seller_wallet":"0x1111111111111111111111111111111111111111","seller_agent_id":"tiedan","amount":"0.3","channel_id":"mock","chain":"bsc"}')
DISPUTE_ID=$(echo "$DISPUTE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('escrow_id',''));")

# 推进到 DELIVERED 状态
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$DISPUTE_ID/fund/confirm \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"buyer_wallet":"0x2222222222222222222222222222222222222222"}' > /dev/null
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$DISPUTE_ID/seller-accept \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"seller_wallet":"0x1111111111111111111111111111111111111111"}' > /dev/null
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$DISPUTE_ID/deliver \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"seller_wallet":"0x1111111111111111111111111111111111111111","result":"poor quality delivery"}' > /dev/null

echo -e "${YELLOW}→ 买家发起争议${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$DISPUTE_ID/dispute \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -d '{"buyer_wallet":"0x2222222222222222222222222222222222222222","reason":"交付质量差，数据不完整"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else \"✗\"} state={d.get(\"state\",\"?\")} (5分钟冷却期: 仲裁等待中)')"

echo -e "${YELLOW}→ 管理员仲裁 (seller_win — 高信誉卖家)${NC}"
echo -e "  ${CYAN}注: 生产环境需要等待5分钟冷却期，demo 模式下直接仲裁${NC}"
curl -s -X POST http://localhost:$API_PORT/api/v1/escrow/$DISPUTE_ID/resolve \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: "$INTERNAL_TOKEN"" \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -d '{"decision":"seller_win","arbiter":"0xAdminWallet","reason":"卖家信誉高(4.2>3.0)，交付虽不完美但可接受"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  {\"✓\" if d.get(\"ok\") else d.get(\"error\",\"✗\")} resolution={d.get(\"resolution\",\"?\")}')" || true

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  ✅ 全协议流程演示完成${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}已完成:${NC}"
echo -e "  1. Agent 注册 + 最佳匹配"
echo -e "  2. Escrow 全流程 (6步状态转换)"
echo -e "  3. Session Key 创建 + 撤销"
echo -e "  4. Voucher 按量计费 (激活→使用→耗尽)"
echo -e "  5. 争议仲裁 (信誉加权)"
echo ""
echo -e "  ${CYAN}API 端点:${NC} http://localhost:$API_PORT"
echo -e "  ${CYAN}健康检查:${NC} http://localhost:$API_PORT/healthz"
echo -e "  ${CYAN}指标:${NC} http://localhost:$API_PORT/metrics"
echo ""
echo -e "  ${YELLOW}按 Ctrl+C 停止服务${NC}"

# 等待退出
trap "echo ''; echo '停止中...'; pkill -f 'api_server.py' 2>/dev/null; pkill -f 'server_modular.js' 2>/dev/null; echo '已停止'; exit 0" INT TERM
wait