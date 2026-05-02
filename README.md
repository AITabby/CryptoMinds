# CryptoMinds

CryptoMinds is an agent economy protocol for autonomous service discovery, hiring, verification, escrow settlement, and dispute resolution.

It is currently **testnet-ready**: the core protocol flows, escrow state machine, verification gates, session keys, vouchers, reputation records, and SQLite/PostgreSQL storage are implemented. Production hardening is still ongoing around non-custodial session key UX, mainnet operations, monitoring, and multi-sig arbitration.

For a higher-level protocol overview, start with [docs/WHITEPAPER.md](docs/WHITEPAPER.md).

---

## Quick Start

Local demo mode is the fastest way to try the full flow:

```bash
cp .env.example .env
bash demo.sh
```

Or start the two services manually:

```bash
python3 api_server.py              # Python API, default :3458
cd web && node server_modular.js   # Express gateway + Web UI, default :3457
```

Open http://localhost:3457 for the Web Dashboard.

---

## Configuration

Development can run from `.env.example` with demo defaults. Staging and production should use explicit secrets and environment-specific config from `environments/`.

Minimum staging/testnet variables:

```bash
CRYPTOMINDS_ENV=staging
DEMO_MODE=false
CRYPTOMINDS_DEBUG=false
CRYPTOMINDS_INTERNAL_TOKEN=<strong-random-token>
ADMIN_SECRET=<strong-random-secret>
BSC_RPC=<testnet-or-provider-rpc>
ESCROW_CONTRACT_ADDRESS=<deployed-service-escrow-address>
DATABASE_URL=postgresql://...
```

Security boundaries:

- Demo placeholders such as `main_private_key: "DEMO"` are only for local demo mode.
- Staging/production write paths require internal service auth, wallet signatures, admin secret, or on-chain state checks depending on the endpoint.
- Do not expose the Python API, PostgreSQL, or agent service ports directly to the public internet.

---

## API Examples

These examples use the Python API directly for local development. In a deployed environment, browser clients should go through the Express gateway.

Set a token once:

```bash
TOKEN=your-token
```

### Escrow Demo Flow

The following mock-channel flow is intended for local demo mode.

```bash
# 1. Create escrow
curl -X POST localhost:3458/api/v1/escrow/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"task_id":"t1","buyer_wallet":"0xB","seller_wallet":"0xS","seller_agent_id":"agent-1","amount":"0.5","channel_id":"mock","chain":"mock"}'

# 2. Replace {id} with the escrow_id returned above.
curl -X POST localhost:3458/api/v1/escrow/{id}/fund/confirm \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"buyer_wallet":"0xB"}'

curl -X POST localhost:3458/api/v1/escrow/{id}/seller-accept \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"seller_wallet":"0xS"}'

curl -X POST localhost:3458/api/v1/escrow/{id}/deliver \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"seller_wallet":"0xS","result":"done"}'

curl -X POST localhost:3458/api/v1/escrow/{id}/verify \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"task_type":"data_delivery","data":"done"}'

curl -X POST localhost:3458/api/v1/escrow/{id}/release \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"buyer_wallet":"0xB"}'
```

On staging/testnet with `bsc-native`, `fund/confirm` validates the on-chain order, and actor actions require wallet signatures.

### Session Key

Local demo mode supports placeholder private keys:

```bash
curl -X POST localhost:3458/api/v1/session-keys/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"main_wallet":"0x1111111111111111111111111111111111111111","main_private_key":"DEMO","agent_id":"a1","chains":["bsc"],"per_tx_limit":"1.0","total_quota":"10.0","actions":["pay"]}'
```

Staging/production rejects `DEMO`, `PLACEHOLDER`, and `TEST` private keys. The production path should use wallet-signed session key authorization instead of sending a main wallet private key.

### Voucher Metered Billing

```bash
curl -X POST localhost:3458/api/v1/voucher/create \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"issuer_wallet":"0xB","agent_id":"tiedan","capability_task_type":"compute_result","unit_price":"0.001","unit_type":"api_call","total_units":100,"chain":"mock","channel_id":"mock"}'

curl -X POST localhost:3458/api/v1/voucher/{id}/activate \
  -H "X-CryptoMinds-Internal-Token: $TOKEN"

curl -X POST localhost:3458/api/v1/voucher/{id}/use \
  -H "Content-Type: application/json" \
  -H "X-CryptoMinds-Internal-Token: $TOKEN" \
  -d '{"units":10}'
```

---

## Testnet Deployment

Docker Compose starts PostgreSQL, the Python API, the Express gateway, and managed agent services:

```bash
docker-compose up -d --build
```

For a public VPS, put Nginx or another reverse proxy in front of the Express gateway:

- expose only `80/443` publicly;
- keep Python API `3458`, PostgreSQL `5432`, and agent ports private;
- use strong `CRYPTOMINDS_INTERNAL_TOKEN` and `ADMIN_SECRET`;
- enable HTTPS before sharing the dashboard URL;
- back up the PostgreSQL volume before upgrades.

---

## Testing

```bash
make test       # pytest + node:test
make pytest     # Python unit tests
make e2e        # end-to-end test script
make lint       # flake8
```

Current local baseline: `294 passed, 1 skipped` for Python tests and `10 passed` for Node tests.

---

## Documentation

Start here depending on what you need:

| Document | Best For | What It Covers |
|----------|----------|----------------|
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | Product and ecosystem overview | Problem, protocol model, market thesis, ecosystem design |
| [docs/WHITEPAPER_TECH_SPEC.md](docs/WHITEPAPER_TECH_SPEC.md) | Technical review | Architecture, state machines, security model, contracts |
| [docs/API.md](docs/API.md) | API integration | Human-readable endpoint docs and examples |
| [docs/openapi.json](docs/openapi.json) | Tooling and SDK generation | Machine-readable API schema |
| [docs/DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md) | Operators | Backup, recovery, and incident checklist |

---

## Project Structure

```text
cryptominds/
├── api_server.py          # Python API
├── protocol.py            # protocol entry points
├── settlement/            # settlement channels and escrow state machine
├── escrow/                # arbitration and slashing logic
├── voucher/               # metered billing vouchers
├── auth/                  # session key model and signing
├── verification/          # verification gates
├── agent/                 # agent capability model and registry
├── reputation/            # performance records, reputation, credit currency
├── data/                  # SQLite/PostgreSQL stores
├── contracts/             # escrow/staking contracts and ABI artifacts
├── web/                   # Express gateway and Web UI
├── agent_runtimes/        # managed agent runtimes
├── monitoring/            # Prometheus/Grafana assets
├── scripts/               # deployment, health, and test scripts
└── docs/                  # whitepaper, API docs, recovery SOP
```

---

## Roadmap

```text
Phase 1 done   Core protocol: escrow, verification gates, agents, reputation
Phase 2 done   Infrastructure: session keys, vouchers, PostgreSQL, monitoring
Phase 3 active Testnet operations, wallet-signed session key UX, multi-sig arbitration
Phase 4 later  Multi-chain expansion, DAO governance, cross-protocol integrations
```

---

## License

MIT
