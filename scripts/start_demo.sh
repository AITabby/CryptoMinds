#!/bin/bash
# CryptoMinds 测试网 Demo 一键启动
#
# 用法:
#   ./scripts/start_demo.sh              # 启动所有服务
#   ./scripts/start_demo.sh --stop       # 停止所有服务
#   ./scripts/start_demo.sh --status     # 查看状态
#
# 首次使用前:
#   1. 部署合约: python3 scripts/deploy_testnet.py
#   2. 安装 cloudflared: brew install cloudflared
#   3. 设置 .env 中的 ESCROW_CONTRACT_ADDRESS

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/.logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[CryptoMinds]${NC} $1"; }
warn() { echo -e "${YELLOW}[CryptoMinds]${NC} $1"; }
err() { echo -e "${RED}[CryptoMinds]${NC} $1"; }

# 加载 .env
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

stop_services() {
    log "停止服务..."
    for pid_file in "$PID_DIR"/*.pid; do
        [ -f "$pid_file" ] || continue
        name=$(basename "$pid_file" .pid)
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && log "$name (PID $pid) 已停止"
        fi
        rm -f "$pid_file"
    done
}

show_status() {
    log "服务状态:"
    all_stopped=true
    for pid_file in "$PID_DIR"/*.pid; do
        [ -f "$pid_file" ] || continue
        name=$(basename "$pid_file" .pid)
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "  $name: 运行中 (PID $pid)"
            all_stopped=false
        else
            warn "  $name: 已停止 (PID $pid 不存在)"
        fi
    done
    if [ "$all_stopped" = true ]; then
        log "  没有服务在运行"
    fi
}

case "${1:-start}" in
    --stop|-s)
        stop_services
        exit 0
        ;;
    --status|-st)
        show_status
        exit 0
        ;;
esac

# 检查前置
if ! command -v python3 &>/dev/null; then
    err "需要 python3"; exit 1
fi

# 检查合约地址
if [ -z "$ESCROW_CONTRACT_ADDRESS" ]; then
    # 尝试从 deployments 读取
    if [ -f "$PROJECT_DIR/deployments/bsc-testnet.json" ]; then
        export ESCROW_CONTRACT_ADDRESS=$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/deployments/bsc-testnet.json'))['contract_address'])")
        log "从 deployments 读取合约地址: $ESCROW_CONTRACT_ADDRESS"
    else
        err "未设置 ESCROW_CONTRACT_ADDRESS"
        err "先运行: python3 scripts/deploy_testnet.py"
        exit 1
    fi
fi

# 1. 启动主 API
log "启动主 API (Flask)..."
cd "$PROJECT_DIR"
FLASK_APP=api_server.py python3 -m flask run --host=127.0.0.1 --port=3458 > "$LOG_DIR/api.log" 2>&1 &
echo $! > "$PID_DIR/api.pid"
sleep 2
if kill -0 $(cat "$PID_DIR/api.pid") 2>/dev/null; then
    log "API 运行在 http://localhost:3458"
else
    err "API 启动失败，查看 $LOG_DIR/api.log"
    cat "$LOG_DIR/api.log"
    exit 1
fi

# 2. 启动信用分 API
log "启动信用分 API..."
CREDIT_SCORE_DB_PATH="$PROJECT_DIR/credit_score/credit_score.db" \
python3 -m credit_score.api > "$LOG_DIR/credit_score.log" 2>&1 &
echo $! > "$PID_DIR/credit_score.pid"
sleep 2
if kill -0 $(cat "$PID_DIR/credit_score.pid") 2>/dev/null; then
    log "信用分 API 运行在 http://localhost:3459"
else
    warn "信用分 API 启动失败，查看 $LOG_DIR/credit_score.log"
fi

# 3. 启动 Cloudflare Tunnel
if command -v cloudflared &>/dev/null; then
    log "启动 Cloudflare Tunnel..."
    cloudflared tunnel --url http://localhost:3458 > "$LOG_DIR/tunnel.log" 2>&1 &
    echo $! > "$PID_DIR/tunnel.pid"
    sleep 5
    # 提取公网 URL
    TUNNEL_URL=$(grep -o 'https://[a-z0-9\-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        log "公网地址: $TUNNEL_URL"
        log "信用分面板: http://localhost:3459"
    else
        warn "Tunnel URL 未获取到，查看 $LOG_DIR/tunnel.log"
    fi
else
    warn "cloudflared 未安装，跳过隧道"
    warn "安装: brew install cloudflared"
    warn "本地访问: http://localhost:3458"
fi

echo ""
log "==============================="
log "CryptoMinds Demo 已启动"
log "==============================="
log "API:       http://localhost:3458"
log "信用分:    http://localhost:3459"
log "合约:      $ESCROW_CONTRACT_ADDRESS"
log "BSCscan:   https://testnet.bscscan.com/address/$ESCROW_CONTRACT_ADDRESS"
[ -n "$TUNNEL_URL" ] && log "公网:      $TUNNEL_URL"
log ""
log "停止: ./scripts/start_demo.sh --stop"
log "状态: ./scripts/start_demo.sh --status"
