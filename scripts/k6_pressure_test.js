/**
 * CryptoMinds k6 Pressure Test
 *
 * Simulates realistic load patterns against all main API endpoints.
 * Run: k6 run scripts/k6_pressure_test.js
 *
 * Env vars (override defaults):
 *   API_HOST       — target host (default: http://localhost:3458)
 *   INTERNAL_TOKEN — auth token
 *   VU_COUNT       — virtual users (default: 20)
 *   DURATION       — test duration (default: 30s)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const latencyTrend = new Trend('latency_ms');

const API_HOST = __ENV.API_HOST || 'http://localhost:3458';
const TOKEN = __ENV.INTERNAL_TOKEN || 'dev-internal-token';
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${TOKEN}`,
  'X-CryptoMinds-Internal-Token': TOKEN,
};

export const options = {
  vus: parseInt(__ENV.VU_COUNT || '20'),
  duration: __ENV.DURATION || '30s',
  thresholds: {
    errors: ['rate<0.15'],         // < 15% error rate
    http_req_duration: ['p(95)<2000'], // 95th percentile < 2s
  },
};

// ── Test data ────────────────────────────────────────

const CHAINS = ['bsc', 'eth', 'sol'];
const TASK_TYPES = ['token_delivery', 'data_delivery', 'compute_result', 'signal_content'];

function randomWallet() {
  return `0x${Array.from({length: 40}, () => Math.floor(Math.random() * 16).toString(16)).join('')}`;
}

function randomId() {
  return `agent-${Math.random().toString(36).slice(2, 8)}`;
}

// ── Scenarios ────────────────────────────────────────

function readInfo() {
  const res = http.get(`${API_HOST}/api/v1/info`, { headers });
  check(res, { 'info 200': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function readAgents() {
  const res = http.get(`${API_HOST}/api/v1/agents`, { headers });
  check(res, { 'agents 200': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function readMarketTasks() {
  const res = http.get(`${API_HOST}/api/v1/market/tasks`, { headers });
  check(res, { 'market 200': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function registerAgent() {
  const agent_id = randomId();
  const body = JSON.stringify({
    agent_id,
    name: `k6-agent-${agent_id}`,
    description: 'k6 pressure test agent',
    wallet: randomWallet(),
    endpoint: `http://localhost:9999/${agent_id}`,
    capabilities: [{
      task_type: TASK_TYPES[Math.floor(Math.random() * TASK_TYPES.length)],
      verification_gate: 'auto',
      supported_chains: [CHAINS[Math.floor(Math.random() * CHAINS.length)]],
      supported_channels: ['native'],
      pricing_model: 'fixed',
      base_price: '0.01',
    }],
    reputation: { score: 50, tasks_completed: 0, tasks_failed: 0, total_volume: '0' },
    staked: '1.0',
    online: true,
  });
  const res = http.post(`${API_HOST}/api/v1/agents/register`, body, { headers });
  check(res, { 'register ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
  return agent_id;
}

function createTask() {
  const body = JSON.stringify({
    task_type: TASK_TYPES[Math.floor(Math.random() * TASK_TYPES.length)],
    buyer_wallet: randomWallet(),
    seller_wallet: randomWallet(),
    amount: '0.01',
    chain: CHAINS[Math.floor(Math.random() * CHAINS.length)],
  });
  const res = http.post(`${API_HOST}/api/v1/tasks/create`, body, { headers });
  check(res, { 'task ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function escrowCreate() {
  const buyer = randomWallet();
  const body = JSON.stringify({
    buyer_wallet: buyer,
    seller_wallet: randomWallet(),
    seller_agent_id: randomId(),
    amount: '0.05',
    channel_id: 'bsc-native',
    chain: 'bsc',
    verification_threshold: 0.7,
  });
  const res = http.post(`${API_HOST}/api/v1/escrow/create`, body, { headers });
  check(res, { 'escrow ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
  return res.json()?.escrow_id;
}

function voucherCreate() {
  const body = JSON.stringify({
    seller_agent_id: randomId(),
    buyer_wallet: randomWallet(),
    service_type: 'compute_result',
    total_units: 100,
    price_per_unit: '0.001',
    chain: 'bsc',
    channel_id: 'bsc-native',
  });
  const res = http.post(`${API_HOST}/api/v1/voucher/create`, body, { headers });
  check(res, { 'voucher ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function healthz() {
  const res = http.get(`${API_HOST}/healthz`);
  check(res, { 'healthz ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

function metrics() {
  const res = http.get(`${API_HOST}/metrics`);
  check(res, { 'metrics ok': r => r.status === 200 });
  errorRate.add(res.status !== 200);
  latencyTrend.add(res.timings.duration);
}

// ── Main test loop ───────────────────────────────────

export default function () {
  const scenario = Math.floor(Math.random() * 10);

  // Weight distribution: heavy on reads, lighter on writes
  switch (scenario) {
    case 0: readInfo(); break;
    case 1: readAgents(); break;
    case 2: readMarketTasks(); break;
    case 3: healthz(); break;
    case 4: metrics(); break;
    case 5: registerAgent(); break;
    case 6: createTask(); break;
    case 7: escrowCreate(); break;
    case 8: voucherCreate(); break;
    case 9:
      // Mixed read-write sequence
      readInfo();
      registerAgent();
      createTask();
      break;
  }

  sleep(Math.random() * 0.5 + 0.1);  // 100–600ms pause between requests
}