/**
 * 协议代理路由
 *
 * 将请求代理到 Python API 服务 (3458)
 * 统一入口，前端只需连接一个端口
 */

const express = require('express');
const router = express.Router();

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:3458';
const INTERNAL_TOKEN = process.env.CRYPTOMINDS_INTERNAL_TOKEN || '';

// 代理请求到 Python 服务
async function proxyToPython(req, res, path) {
  try {
    const headers = {
      'Content-Type': 'application/json',
    };

    if (INTERNAL_TOKEN) {
      headers['X-CryptoMinds-Internal-Token'] = INTERNAL_TOKEN;
    }

    const options = {
      method: req.method,
      headers,
    };

    if (req.method !== 'GET' && req.body) {
      options.body = JSON.stringify(req.body);
    }

    const response = await fetch(`${PYTHON_API_URL}${path}`, options);
    const data = await response.json();

    res.status(response.status).json(data);
  } catch (err) {
    console.error(`[proxy] Python API error: ${err.message}`);
    res.json({ ok: false, error: 'Python API 服务不可用', details: err.message });
  }
}

// ── 协议信息 ─────────────────────────────────────

router.get('/protocol/info', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/info');
});

router.get('/protocol/channels', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/channels');
});

router.get('/protocol/gates', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/gates');
});

// ── Agent 协议 ───────────────────────────────────

router.post('/protocol/agents/register', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/agents/register');
});

router.get('/protocol/agents/:agentId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}`);
});

router.get('/protocol/agents/:agentId/reputation', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/reputation`);
});

router.post('/protocol/agents/:agentId/reputation/update', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/reputation/update`);
});

router.get('/protocol/agents/:agentId/records', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/records`);
});

// ── 任务协议 ─────────────────────────────────────

router.post('/protocol/tasks/create', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/create');
});

router.post('/protocol/tasks/verify', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/verify');
});

router.post('/protocol/tasks/complete', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/complete');
});

// ── Agent 自主下单 ───────────────────────────────

router.post('/protocol/agent-buy', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/agent-buy');
});

router.get('/protocol/agents/best-match', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/best-match?${new URLSearchParams(req.query).toString()}`);
});

// ── 市场任务 ─────────────────────────────────────

router.get('/protocol/market/tasks', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/market/tasks');
});

router.post('/protocol/market/tasks', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/market/tasks');
});

// ── 信用货币 ─────────────────────────────────────

router.post('/protocol/credit/issue', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/credit/issue');
});

router.get('/protocol/credit', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/credit');
});

router.post('/protocol/credit/:currencyId/accept', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/credit/${req.params.currencyId}/accept`);
});

module.exports = { createProtocolRoutes: () => router };
