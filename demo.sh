#!/bin/bash
# CryptoMinds 一键演示脚本
# 启动平台 + 卖家Agent + 自动下单Demo

set -e
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   CryptoMinds — 一键演示             ║${NC}"
echo -e "${CYAN}║   AI Agent 链上雇佣平台               ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# 清理旧进程
echo -e "${YELLOW}[1/4]${NC} 清理旧进程..."
pkill -f "agent_server.py" 2>/dev/null || true
pkill -f "server.js" 2>/dev/null || true
sleep 1

# 启动卖家Agent
echo -e "${YELLOW}[2/4]${NC} 启动卖家Agent微服务..."
export CRYPTOMINDS_DEMO=1
python3 agents/agent_server.py --agent tiedan --port 5001 &
python3 agents/agent_server.py --agent choudan --port 5002 &
python3 agents/agent_server.py --agent ludan --port 5003 &
sleep 2

# 健康检查
echo -e "${YELLOW}[3/4]${NC} 健康检查..."
OK=0
for port in 5001 5002 5003; do
  if curl -sf http://localhost:$port/health > /dev/null 2>&1; then
    AGENT=$(curl -sf http://localhost:$port/health | python3 -c "import sys,json;print(json.load(sys.stdin).get('agent','?'))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}✓${NC} 端口 $port ($AGENT) 正常"
    OK=$((OK+1))
  else
    echo -e "  ${RED}✗${NC} 端口 $port 无响应"
  fi
done

if [ $OK -eq 0 ]; then
  echo -e "${RED}所有Agent启动失败，退出${NC}"
  exit 1
fi

# 启动Web平台
echo -e "${YELLOW}[4/4]${NC} 启动Web平台 (端口3457)..."
export DEMO_MODE=true
node web/server.js &
sleep 2

if curl -sf http://localhost:3457 > /dev/null 2>&1; then
  echo ""
  echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║   ✅ 全部启动成功！                   ║${NC}"
  echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${CYAN}平台地址:${NC} http://localhost:3457"
  echo -e "  ${CYAN}模式:${NC} DEMO (跳过链上验证，模拟执行)"
  echo -e "  ${CYAN}卖家Agent:${NC} $OK 个在线"
  echo ""
  echo -e "  ${YELLOW}演示流程:${NC}"
  echo "  1. 连接钱包 → 注册买家Agent"
  echo "  2. 一句话描述需求 → Agent自动匹配卖家"
  echo "  3. 确认支付 → 卖家Agent执行买币"
  echo "  4. 确认收货 → 评分 → 权重更新"
  echo ""
  echo -e "  按 Ctrl+C 停止所有服务"
  echo ""
else
  echo -e "${RED}Web平台启动失败${NC}"
  exit 1
fi

# 等待退出
trap "echo ''; echo '停止中...'; pkill -f 'agent_server.py' 2>/dev/null; pkill -f 'server.js' 2>/dev/null; echo '已停止'; exit 0" INT TERM
wait
