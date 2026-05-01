# CryptoMinds — multi-process deployment
# Python 3.9+ + Node.js 18+ in a single image

# Stage 1: Python dependencies
FROM python:3.9-slim AS python-base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Node.js dependencies
FROM node:18-slim AS node-base
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --production

# Stage 3: Runtime image
FROM node:18-slim

# Install Python from system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Create venv and install Python deps
WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"

# Copy Node.js deps from stage 2
COPY --from=node-base /app/web/node_modules /app/web/node_modules

# Copy application source
COPY . .

# Install web npm deps (covers any differences from stage 2)
WORKDIR /app/web
RUN npm install --production
WORKDIR /app

# Expose ports
EXPOSE 3457 3458 5001 5002 5003 5004

# Do NOT copy secrets into image
# wallets.json, .env, web/cryptominds.db are injected via volumes/env/secrets

# Default: start web API + Python API
ENV PORT=3457
ENV CRYPTOMINDS_API_PORT=3458
ENV PYTHON_API_URL=http://localhost:3458
ENV CRYPTOMINDS_DEMO=0

CMD ["sh", "-c", "python3 api_server.py & sleep 2 && node web/server_modular.js"]