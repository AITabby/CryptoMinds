/**
 * 协议代理路由
 *
 * 将请求代理到 Python API 服务 (3458)
 * 统一入口，前端只需连接一个端口
 *
 * 安全策略 (分层注入):
 * - GET (只读): Express 始终注入 internal token (读操作安全)
 * - requireAdmin 路由: Express 先验证 admin secret → 通过后注入 internal token + 转发 admin secret
 * - 业务鉴权路由 (Escrow dispute, Session Key): Express 注入 internal token, 业务逻辑鉴权在 Python 层完成
 * - 内部写入路由 (tasks/complete, agents/register 等): 不注入 internal token, 仅允许服务端内部调用
 */

const express = require('express');
const router = express.Router();
const crypto = require('crypto');

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:3458';
const INTERNAL_TOKEN = process.env.CRYPTOMINDS_INTERNAL_TOKEN || '';
const ADMIN_SECRET = process.env.ADMIN_SECRET || '';

// ── 认证中间件 ───────────────────────────────────────

function requireAdmin(req, res, next) {
  if (!ADMIN_SECRET) {
    return res.json({ ok: false, error: '管理员认证未配置 (ADMIN_SECRET)' });
  }
  const supplied = req.headers['x-admin-secret'] || req.body.adminSecret;
  if (!supplied) {
    return res.json({ ok: false, error: '需要管理员密钥 (X-Admin-Secret)' });
  }
  const suppliedBuf = Buffer.from(supplied, 'utf8');
  const secretBuf = Buffer.from(ADMIN_SECRET, 'utf8');
  if (suppliedBuf.length === secretBuf.length &&
      crypto.timingSafeEqual(suppliedBuf, secretBuf)) {
    req._adminVerified = true;
    return next();
  }
  return res.json({ ok: false, error: '管理员密钥错误' });
}

// ── 代理核心 ─────────────────────────────────────────

// injectToken: 是否注入 internal token (GET/已认证路由 = true, 内部写入路由 = false)
// forwardAdminSecret: 是否转发 admin secret 到 Python (admin 路由 = true)
async function proxyToPython(req, res, path, { injectToken = false, forwardAdminSecret = false } = {}) {
  try {
    const headers = {
      'Content-Type': 'application/json',
    };

    if (injectToken && INTERNAL_TOKEN) {
      headers['X-CryptoMinds-Internal-Token'] = INTERNAL_TOKEN;
    }

    // 转发已验证的 admin secret 到 Python
    if (forwardAdminSecret && req._adminVerified && ADMIN_SECRET) {
      headers['X-Admin-Secret'] = ADMIN_SECRET;
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

// ── 协议信息 (只读, 注入 token) ────────────────────

router.get('/protocol/info', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/info', { injectToken: true });
});

router.get('/protocol/channels', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/channels', { injectToken: true });
});

router.get('/protocol/gates', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/gates', { injectToken: true });
});

// ── Agent 协议 ───────────────────────────────────────
// register/reputation/update 是内部写入, 不从浏览器注入 token
// GET 只读, 注入 token

router.post('/protocol/agents/register', async (req, res) => {
  // 内部写入: 不注入 token, 需服务端直接调用 Python
  await proxyToPython(req, res, '/api/v1/agents/register');
});

router.get('/protocol/agents/:agentId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}`, { injectToken: true });
});

router.get('/protocol/agents/:agentId/reputation', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/reputation`, { injectToken: true });
});

router.post('/protocol/agents/:agentId/reputation/update', async (req, res) => {
  // 内部写入: 不注入 token
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/reputation/update`);
});

router.get('/protocol/agents/:agentId/records', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/${req.params.agentId}/records`, { injectToken: true });
});

// ── 任务协议 (内部写入, 不从浏览器注入 token) ────────

router.post('/protocol/tasks/create', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/create');
});

router.post('/protocol/tasks/verify', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/verify');
});

router.post('/protocol/tasks/complete', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/tasks/complete');
});

// ── Agent 自主下单 (内部写入) ────────────────────────

router.post('/protocol/agent-buy', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/agent-buy');
});

router.get('/protocol/agents/best-match', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/agents/best-match?${new URLSearchParams(req.query).toString()}`, { injectToken: true });
});

// ── 市场任务 ────────────────────────────────────────

router.get('/protocol/market/tasks', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/market/tasks', { injectToken: true });
});

router.post('/protocol/market/tasks', async (req, res) => {
  // 内部写入: 不注入 token
  await proxyToPython(req, res, '/api/v1/market/tasks');
});

// ── 信用货币 (内部写入) ────────────────────────────

router.post('/protocol/credit/issue', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/credit/issue');
});

router.get('/protocol/credit', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/credit', { injectToken: true });
});

router.post('/protocol/credit/:currencyId/accept', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/credit/${req.params.currencyId}/accept`);
});

// ── Escrow 争议解决 ──────────────────────────────
// create + resolve: requireAdmin → 验证后注入 token + 转发 admin secret
// dispute: 业务鉴权在 Python 层完成, 注入 token
// GET: 注入 token

router.post('/protocol/escrow/create', requireAdmin, async (req, res) => {
  await proxyToPython(req, res, '/api/v1/escrow/create', { injectToken: true, forwardAdminSecret: true });
});

router.get('/protocol/escrow/:escrowId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/dispute', async (req, res) => {
  // 业务鉴权 (wallet 签名等) 在 Python 层完成
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/dispute`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/resolve', requireAdmin, async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/resolve`, { injectToken: true, forwardAdminSecret: true });
});

router.get('/protocol/escrow/disputed', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/escrow/disputed', { injectToken: true });
});

// ── Escrow 正向路径 (生命周期) ──────────────────────
// 业务鉴权在 Python 层完成, 注入 token

router.post('/protocol/escrow/:escrowId/fund/prepare', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/fund/prepare`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/fund/confirm', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/fund/confirm`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/seller-accept', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/seller-accept`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/deliver', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/deliver`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/verify', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/verify`, { injectToken: true });
});

router.post('/protocol/escrow/:escrowId/release', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/escrow/${req.params.escrowId}/release`, { injectToken: true });
});

// ── Session Key 授权 ──────────────────────────────
// 业务鉴权 (wallet 匹配/ECDSA 签名) 在 Python 层完成
// 注入 token 让 @require_auth 通过, 实际权限控制在 Python 业务逻辑

router.post('/protocol/session-keys/create', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/session-keys/create', { injectToken: true });
});

router.get('/protocol/session-keys/:keyId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/session-keys/${req.params.keyId}`, { injectToken: true });
});

router.post('/protocol/session-keys/:keyId/revoke', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/session-keys/${req.params.keyId}/revoke`, { injectToken: true });
});

router.post('/protocol/session-keys/:keyId/increase-quota', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/session-keys/${req.params.keyId}/increase-quota`, { injectToken: true });
});

router.get('/protocol/session-keys/agent/:agentId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/session-keys/agent/${req.params.agentId}`, { injectToken: true });
});

// ── Voucher 按量计费 ──────────────────────────────
// 业务鉴权在 Python 层完成, 注入 token
// resolve: requireAdmin → 验证后注入 token + 转发 admin secret

router.post('/protocol/voucher/create', async (req, res) => {
  await proxyToPython(req, res, '/api/v1/voucher/create', { injectToken: true });
});

router.get('/protocol/voucher/:voucherId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/${req.params.voucherId}`, { injectToken: true });
});

router.post('/protocol/voucher/:voucherId/activate', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/${req.params.voucherId}/activate`, { injectToken: true });
});

router.post('/protocol/voucher/:voucherId/use', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/${req.params.voucherId}/use`, { injectToken: true });
});

router.post('/protocol/voucher/:voucherId/dispute', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/${req.params.voucherId}/dispute`, { injectToken: true });
});

router.post('/protocol/voucher/:voucherId/resolve', requireAdmin, async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/${req.params.voucherId}/resolve`, { injectToken: true, forwardAdminSecret: true });
});

router.get('/protocol/voucher/agent/:agentId', async (req, res) => {
  await proxyToPython(req, res, `/api/v1/voucher/agent/${req.params.agentId}`, { injectToken: true });
});

module.exports = { createProtocolRoutes: () => router };