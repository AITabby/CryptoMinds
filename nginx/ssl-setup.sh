#!/bin/bash
# CryptoMinds SSL certificate setup using acme.sh (Let's Encrypt)
set -e

DOMAIN="${1:?Usage: ssl-setup.sh <domain>}"
EMAIL="${2:?Usage: ssl-setup.sh <domain> <email>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$PROJECT_ROOT/nginx/ssl"

echo "[SSL] Setting up certificate for $DOMAIN"

# Install acme.sh if not present
if ! command -v acme.sh &>/dev/null; then
    echo "[SSL] Installing acme.sh..."
    curl -s https://get.acme.sh | sh -s email="$EMAIL"
    source ~/.bashrc
fi

# Create SSL directory
mkdir -p "$SSL_DIR"

# Issue certificate (DNS mode recommended for production)
# If using DNS API (Cloudflare, Route53, etc), set the relevant env vars first.
# Example for standalone mode (requires port 80 to be free):
echo "[SSL] Issuing certificate..."
~/.acme.sh/acme.sh --issue -d "$DOMAIN" --standalone --email "$EMAIL"

# Install certificate to project
~/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
    --key-file       "$SSL_DIR/cryptominds.key" \
    --fullchain-file "$SSL_DIR/cryptominds.pem" \
    --reloadcmd      "docker-compose restart nginx"

echo "[SSL] Certificate installed at $SSL_DIR/"
echo "[SSL] Certificate will auto-renew via acme.sh cron job"
echo ""
echo "[SSL] Next steps:"
echo "  1. Update nginx.conf server_name to $DOMAIN"
echo "  2. docker-compose up -d nginx"
echo "  3. Verify: curl https://$DOMAIN/healthz"