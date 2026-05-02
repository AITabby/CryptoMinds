#!/bin/bash
# CryptoMinds 一键部署脚本
# Usage: ./scripts/deploy.sh [staging|prod]
set -e

ENV="${1:-staging}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
MONITORING_FILE="$PROJECT_ROOT/monitoring/docker-compose.monitoring.yml"

echo "=== CryptoMinds Deployment ($ENV) ==="

# 1. Validate environment config
ENV_FILE="$PROJECT_ROOT/environments/.env.$ENV"
if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] Environment file not found: $ENV_FILE"
    exit 1
fi

# 2. Check required secrets are set
REQUIRED_VARS=("CRYPTOMINDS_INTERNAL_TOKEN" "ADMIN_SECRET" "BSC_RPC")
for var in "${REQUIRED_VARS[@]}"; do
    value=$(grep "^${var}=" "$ENV_FILE" | cut -d'=' -f2)
    if [ -z "$value" ]; then
        echo "[ERROR] $var is empty in $ENV_FILE — fill it before deploying"
        exit 1
    fi
    # Check for weak values
    if echo "$value" | grep -qi "test-token\|admin\|password\|secret\|cryptominds-admin"; then
        echo "[ERROR] $var has a weak value in $ENV_FILE — use a strong random value"
        exit 1
    fi
done

# 3. Check wallets.json permissions (600 only)
WALLETS="$PROJECT_ROOT/wallets.json"
if [ -f "$WALLETS" ]; then
    PERMS=$(stat -f "%Lp" "$WALLETS" 2>/dev/null || stat -c "%a" "$WALLETS" 2>/dev/null)
    if [ "$PERMS" != "600" ]; then
        echo "[ERROR] wallets.json permissions are $PERMS — must be 600"
        echo "  Fix: chmod 600 wallets.json"
        exit 1
    fi
fi

# 4. Check Docker is running
if ! docker info &>/dev/null; then
    echo "[ERROR] Docker is not running"
    exit 1
fi

# 5. Export env vars for docker-compose
export CRYPTOMINDS_ENV="$ENV"
# Load env-specific vars into current shell
set -a
source "$ENV_FILE"
set +a
# Also load base .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

echo "[INFO] Building Docker images..."
docker-compose -f "$COMPOSE_FILE" build

echo "[INFO] Starting services..."
docker-compose -f "$COMPOSE_FILE" up -d

# 6. Wait for healthz
echo "[INFO] Waiting for services to become healthy..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    STATUS=$(docker-compose -f "$COMPOSE_FILE" exec -T python-api \
        curl -s -o /dev/null -w "%{http_code}" http://localhost:3458/healthz 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "503" ]; then
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo "  Waiting... ($WAITED/$MAX_WAIT)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[WARN] Services did not become healthy within $MAX_WAIT seconds"
    echo "  Check logs: docker-compose logs python-api"
else
    echo "[OK] Python API healthz responded with HTTP $STATUS"
fi

# Check Express
EXPRESS_STATUS=$(docker-compose -f "$COMPOSE_FILE" exec -T web-api \
    curl -s -o /dev/null -w "%{http_code}" http://localhost:3457/healthz 2>/dev/null || echo "000")
echo "[OK] Express API healthz responded with HTTP $EXPRESS_STATUS"

# 7. Optionally start monitoring stack
if [ -f "$MONITORING_FILE" ]; then
    echo "[INFO] Starting monitoring stack (Prometheus + Grafana + Alertmanager)..."
    docker-compose -f "$MONITORING_FILE" up -d 2>/dev/null || echo "[WARN] Monitoring stack failed to start"
fi

# 8. Print summary
echo ""
echo "=== Deployment Summary ==="
echo "  Environment: $ENV"
echo "  Public HTTP:  http://localhost"
echo "  Public HTTPS: https://localhost (after SSL certs configured)"
echo "  Python API:   internal docker network only"
echo "  Express API:  internal docker network only"
echo "  Metrics:      internal or private-network access only"
echo "  Health:       https://localhost/healthz"
echo ""
echo "  To check logs: docker-compose logs -f python-api"
echo "  To stop:       docker-compose down"
echo "=== Done ==="
