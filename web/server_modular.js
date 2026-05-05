/**
 * CryptoMinds API Server
 *
 * 模块化版本：
 * - 数据层：SQLite
 * - 路由层：分离到独立文件
 * - 服务层：lib/
 */

// 环境配置（最先加载，确保其他模块读到正确 env）
const { loadEnvironment } = require('./lib/env_loader');
const envConfig = loadEnvironment();

const express = require('express');
const { Web3 } = require('web3');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const webpush = require('web-push');
const morgan = require('morgan');
const { render: renderMetrics, metricsMiddleware } = require('./lib/metrics');

// 数据层
const { getDataStore } = require('./lib/datastore');
const { createSellersStore, createSellersMarketHandlers } = require('./lib/sellers_market_sqlite');
const { getEscrowAddress, getEscrowContract, getEscrowStats, deployEscrow } = require('./lib/escrow');

// 路由
const { createNotificationRoutes } = require('./routes/notification');
const { createAgentRoutes } = require('./routes/agent');
const { createAgentBuyHandlers } = require('./lib/agent_buy');
const { createPaymentRoutes } = require('./routes/payment');
const { createMarketRoutes } = require('./routes/market');
const { createOrderRoutes } = require('./routes/order');
const { createAdminRoutes } = require('./routes/admin');
const { createProtocolRoutes } = require('./routes/protocol');

// ── 配置 ─────────────────────────────────────────

const PORT = process.env.PORT || 3457;
const BSC_RPC = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:3458';
const MINIMAX_API_KEY = process.env.MINIMAX_API_KEY || '';
const MINIMAX_BASE_URL = 'https://api.minimaxi.com/v1';
const DEMO_MODE = process.env.DEMO_MODE === 'true';
const DEMO_WALLET = process.env.DEMO_WALLET || '';
const DEPOSIT_POOL_ADDRESS = process.env.DEPOSIT_POOL_ADDRESS || '';

if (!DEPOSIT_POOL_ADDRESS && process.env.CRYPTOMINDS_ENV === 'prod') {
  console.error('FATAL: DEPOSIT_POOL_ADDRESS is not set. Refusing to start.');
  process.exit(1);
}
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const VAPID_PUBLIC_KEY = process.env.VAPID_PUBLIC_KEY || '';
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY || '';

const SDK_DIR = path.join(__dirname, 'agentpay_sdk');
const MANAGED_X402_SCRIPT = path.join(__dirname, 'scripts', 'managed_x402_payment.py');
const SMART_ROUTER_SCRIPT = path.join(SDK_DIR, 'smart_router.py');
const projectRoot = path.join(__dirname, '..');

// Web3
const w3 = new Web3(BSC_RPC);

// Web Push 配置
if (VAPID_PUBLIC_KEY && VAPID_PRIVATE_KEY) {
  webpush.setVapidDetails('mailto:cryptominds@four.meme', VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);
}

// App
const app = express();

// ── 数据存储 ─────────────────────────────────────

// 使用 datastore.js 的全局实例（单例模式）

// ── 辅助函数 ─────────────────────────────────────

let bnbPriceUsd = 600;
let bnbPriceLastFetch = 0;

async function fetchBnbPrice() {
  const now = Date.now();
  if (now - bnbPriceLastFetch < 60000) return bnbPriceUsd;
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd');
    const data = await res.json();
    if (data.binancecoin?.usd) {
      bnbPriceUsd = data.binancecoin.usd;
      bnbPriceLastFetch = now;
    }
  } catch (e) {}
  return bnbPriceUsd;
}

function getWallets() {
  const walletsFile = path.join(__dirname, '..', 'wallets.json');
  try {
    if (fs.existsSync(walletsFile)) {
      const raw = JSON.parse(fs.readFileSync(walletsFile, 'utf8'));
      const safe = {};
      for (const [name, info] of Object.entries(raw)) {
        safe[name] = { address: info.address };
      }
      return safe;
    }
  } catch (e) {}
  return {};
}

function getWalletForSigning(name) {
  const walletsFile = path.join(__dirname, '..', 'wallets.json');
  try {
    const raw = JSON.parse(fs.readFileSync(walletsFile, 'utf8'));
    const info = raw[name];
    if (!info) return null;
    let pk = info.private_key || info.privateKey || info.key || '';
    if (pk && !pk.startsWith('0x')) pk = '0x' + pk;
    return { address: info.address, private_key: pk };
  } catch (e) { return null; }
}

const MANAGED_AGENT_META = {
  gangdan: { name: 'Buyer Agent', role: '买家代理', icon: '🤖' },
  tiedan: { name: 'Momentum One', role: '趋势策略', icon: '📈' },
  choudan: { name: 'Dip Hunter', role: '低吸策略', icon: '🎯' },
  pidan: { name: 'Risk Sentinel', role: '风控策略', icon: '🛡️' },
  ludan: { name: 'Flow Surfer', role: '流动性策略', icon: '🌊' },
  four_meme: { name: 'Settlement Engine', role: '结算节点', icon: '⚙️' },
};

function getManagedAgents() {
  const wallets = getWallets();
  const agents = {};
  for (const [key, wallet] of Object.entries(wallets)) {
    if (!wallet?.address) continue;
    const meta = MANAGED_AGENT_META[key] || { name: key, role: '托管钱包', icon: '🤖' };
    agents[key] = { ...meta, addr: wallet.address };
  }
  return agents;
}

async function sendPushNotification(wallet, payload) {
  const store = await getDataStore();
  const subs = await store.getPushSubs(wallet);
  for (const sub of subs) {
    try {
      const subscription = {
        endpoint: sub.endpoint,
        keys: { p256dh: sub.p256dh, auth: sub.auth },
      };
      await webpush.sendNotification(subscription, JSON.stringify(payload));
    } catch (err) {
      if (err.statusCode === 410) {
        await store.deletePushSub(sub.endpoint);
      }
    }
  }
}

app.use(metricsMiddleware);

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, 'public')));
// Request logging (JSON format, skip health checks)
app.use(morgan('json', { skip: (req) => req.path === '/healthz' || req.path === '/metrics' }));

// CORS（生产环境限制来源）
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || '*').split(',').filter(Boolean);
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (ALLOWED_ORIGINS.includes('*')) {
    res.header('Access-Control-Allow-Origin', '*');
  } else if (origin && ALLOWED_ORIGINS.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
  }
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-402-Payment, X-Admin-Secret, X-Admin-Wallet, X-CryptoMinds-Internal-Token');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// ── Rate limiting ─────────────────────────────────────
const rateLimit = require('express-rate-limit');
const RATE_LIMIT_PER_MINUTE = parseInt(process.env.RATE_LIMIT_PER_MINUTE || '60', 10);
const _isDemo = process.env.DEMO_MODE === 'true' || process.env.CRYPTOMINDS_DEBUG === 'true';

const globalLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: RATE_LIMIT_PER_MINUTE,
  standardHeaders: true,
  legacyHeaders: false,
  message: { ok: false, error: '请求频率过高，请稍后再试' },
  skip: (req) => _isDemo || req.path === '/healthz' || req.path === '/metrics',
});

const adminLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { ok: false, error: '管理员操作频率过高' },
  skip: (req) => _isDemo,
});

app.use(globalLimiter);
// Admin routes get stricter limits (applied in route handlers via requireAdmin)

function timingSafeEqualString(a, b) {
  const aBuf = Buffer.from(String(a || ''), 'utf8');
  const bBuf = Buffer.from(String(b || ''), 'utf8');
  return aBuf.length === bBuf.length && crypto.timingSafeEqual(aBuf, bBuf);
}

function hasInternalToken(req) {
  const expected = process.env.CRYPTOMINDS_INTERNAL_TOKEN || '';
  const supplied = req.headers['x-cryptominds-internal-token'] || '';
  return Boolean(expected && supplied && timingSafeEqualString(supplied, expected));
}

function hasAdminSecret(req) {
  const expected = process.env.ADMIN_SECRET || '';
  const supplied = req.headers['x-admin-secret'] || req.body?.adminSecret || '';
  return Boolean(expected && supplied && timingSafeEqualString(supplied, expected));
}

function normalizeWallet(wallet) {
  return String(wallet || '').trim().toLowerCase();
}

function directActionMessage(action, target, wallet) {
  return [
    'CryptoMinds direct action',
    `Action: ${action}`,
    `Target: ${target}`,
    `Wallet: ${normalizeWallet(wallet)}`,
  ].join('\n');
}

function verifyDirectWalletSignature(req, wallet, action, target) {
  const expectedWallet = normalizeWallet(wallet);
  const message = req.body?.message || '';
  const signature = req.body?.signature || '';
  if (!expectedWallet || !message || !signature) return false;
  if (message !== directActionMessage(action, target, expectedWallet)) return false;
  try {
    const recovered = w3.eth.accounts.recover(message, signature);
    return normalizeWallet(recovered) === expectedWallet;
  } catch {
    return false;
  }
}

function requireDirectWriteAuth({ action, target, wallet } = {}) {
  return (req, res, next) => {
    if (DEMO_MODE || hasInternalToken(req) || hasAdminSecret(req)) {
      return next();
    }
    const resolvedAction = typeof action === 'function' ? action(req) : action;
    const resolvedTarget = typeof target === 'function' ? target(req) : target;
    const resolvedWallet = typeof wallet === 'function' ? wallet(req) : wallet;
    if (verifyDirectWalletSignature(req, resolvedWallet, resolvedAction, resolvedTarget)) {
      return next();
    }
    return res.status(403).json({
      ok: false,
      error: '需要 internal token、管理员密钥或钱包签名',
      expectedMessage: directActionMessage(resolvedAction, resolvedTarget, resolvedWallet),
    });
  };
}

// ── 路由注册 ─────────────────────────────────────

async function setupRoutes() {
  const store = await getDataStore();

  // 设置全局数据存储
  app.locals.dataStore = store;

  // 市场路由
  app.use('/api/v1', createMarketRoutes({
    getSellers: () => store.getSellers(),
    getPurchases: () => store.getPurchases(),
    getTxs: () => store.getTxLogs(),
    addTx: (tx) => store.saveTxLog(tx),
    getEscrowAddress,
    getEscrowStats,
    w3,
    fetchBnbPrice,
  }));

  // 通知路由
  app.use('/api/v1', createNotificationRoutes({
    getNotifications: (wallet, limit) => store.getNotifications(wallet, limit),
    markNotificationRead: (id) => store.markNotificationRead(id),
    markAllNotificationsRead: (wallet) => store.markAllNotificationsRead(wallet),
    getPushSubs: (wallet) => store.getPushSubs(wallet),
    savePushSub: (wallet, sub) => store.savePushSub(wallet, sub),
    VAPID_PUBLIC_KEY,
  }));

  // Agent 路由
  app.use('/api/v1', createAgentRoutes({
    getAgents: () => store.getAgents(),
    saveAgent: (agent) => store.saveAgent(agent),
    getAgent: (id) => store.getAgent(id),
    getPurchases: () => store.getPurchases(),
    getSellers: () => store.getSellers(),
    MINIMAX_API_KEY,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL: process.env.MINIMAX_MODEL,  // 可配置模型
    demoMode: DEMO_MODE,
    DEMO_WALLET,
    w3,
  }));

  // 支付路由
  app.use('/api/v1', createPaymentRoutes({
    PYTHON_BIN,
    SDK_DIR,
    MANAGED_X402_SCRIPT,
    X402_VERIFY_SCRIPT: path.join(SDK_DIR, 'x402_verify.py'),
    SMART_ROUTER_SCRIPT,
    demoMode: DEMO_MODE,
    w3,
    getWallets,
  }));

  // 订单路由
  app.use('/api/v1', createOrderRoutes({
    getPurchases: () => store.getPurchases(),
    getPurchase: (id) => store.getPurchase(id),
    updatePurchase: (id, updates) => store.updatePurchase(id, updates),
    savePurchase: (p) => store.savePurchase(p),
    getNotifications: (wallet, limit) => store.getNotifications(wallet, limit),
    addNotification: (n) => store.saveNotification(n),
    sendPushNotification,
    demoMode: DEMO_MODE,
  }));

  // 管理路由
  app.use('/api/v1', createAdminRoutes({
    PYTHON_BIN,
    projectRoot,
    depositPoolAddress: DEPOSIT_POOL_ADDRESS,
    demoMode: DEMO_MODE,
    deployEscrow,
    getEscrowAddress,
    getEscrowStats,
    w3,
    getWallets,
    getManagedAgents,
  }));

  // 协议路由（代理到 Python 服务）
  app.use('/api/v1', createProtocolRoutes());

  // 卖家市场 handlers（直接挂载）
  const sellersStore = createSellersStore(projectRoot);
  const sellersMarketHandlers = createSellersMarketHandlers({
    getSellers: sellersStore,
    saveSellers: () => {},
    getPurchases: () => store.getPurchases(),
    savePurchases: (p) => store.savePurchase(p),
    addTx: (tx) => store.saveTxLog(tx),
    pythonBin: PYTHON_BIN,
    execFileSync,
    w3,
    depositPoolAddress: DEPOSIT_POOL_ADDRESS,
    demoMode: DEMO_MODE,
  });

  app.get('/api/v1/sellers', sellersMarketHandlers.listSellers);
  app.post('/api/v1/sellers/register', requireDirectWriteAuth({
    action: 'seller_register',
    target: (req) => req.body.wallet || '',
    wallet: (req) => req.body.wallet || '',
  }), sellersMarketHandlers.registerSeller);
  app.post('/api/v1/sellers/:wallet/deposit', requireDirectWriteAuth({
    action: 'seller_deposit',
    target: (req) => req.params.wallet,
    wallet: (req) => req.params.wallet,
  }), sellersMarketHandlers.depositSeller);
  app.post('/api/v1/orders/create', requireDirectWriteAuth({
    action: 'order_create',
    target: (req) => `${req.body.buyerWallet || ''}:${req.body.sellerWallet || ''}:${req.body.amount || ''}`,
    wallet: (req) => req.body.buyerWallet || '',
  }), sellersMarketHandlers.createOrder);
  app.post('/api/v1/sellers/exit', requireDirectWriteAuth({
    action: 'seller_exit',
    target: (req) => req.body.wallet || '',
    wallet: (req) => req.body.wallet || '',
  }), sellersMarketHandlers.exitSeller);
  app.post('/api/v1/orders/:id/execute', requireDirectWriteAuth({
    action: 'order_execute',
    target: (req) => req.params.id,
    wallet: (req) => req.body.sellerWallet || '',
  }), sellersMarketHandlers.executeOrder);
  app.post('/api/v1/rate-order', requireDirectWriteAuth({
    action: 'rate_order',
    target: (req) => req.body.orderId || '',
    wallet: (req) => req.body.buyerWallet || req.body.wallet || '',
  }), sellersMarketHandlers.rateOrder);

  // Agent 自主下单（从 agent_buy.js）
  const { pickSellerHandler, agentBuyHandler } = createAgentBuyHandlers({
    fetchImpl: fetch,
    minimaxApiKey: MINIMAX_API_KEY,
    minimaxBaseUrl: MINIMAX_BASE_URL,
    pythonBin: PYTHON_BIN,
    execFileSync,
    getSellers: sellersStore,
    saveSellers: () => {},
    getAgents: () => store.getAgents(),
    addPurchase: (p) => store.savePurchase(p),
    addTx: (tx) => store.saveTxLog(tx),
  });
  app.post('/api/v1/agents/:wallet/pick-seller', pickSellerHandler);
  app.post('/api/v1/agent-buy', agentBuyHandler);
}

// ── API versioning: redirect /api/* → /api/v1/* (back-compat) ──
app.use('/api', (req, res, next) => {
  if (!req.path.startsWith('/v1')) {
    res.redirect(301, `/api/v1${req.path}`);
  } else {
    next();
  }
});

// ── 基础路由 ─────────────────────────────────────

app.get('/', async (req, res) => {
  const bnbPrice = await fetchBnbPrice();
  res.render('index', {
    bnbPrice,
    escrowAddress: getEscrowAddress() || '',
    demoMode: DEMO_MODE,
  });
});

app.get('/healthz', async (req, res) => {
  const checks = {};

  // Check Python API
  try {
    const pyResp = await fetch(`${PYTHON_API_URL}/healthz`, { signal: AbortSignal.timeout(3000) });
    checks.python_api = { status: pyResp.ok ? 'ok' : 'down', url: PYTHON_API_URL };
  } catch (e) {
    checks.python_api = { status: 'down', url: PYTHON_API_URL, error: e.message };
  }

  // Check SQLite
  try {
    const store = await getDataStore();
    const sellers = await store.getSellers();
    checks.database = { status: 'ok', sellers_count: sellers.length };
  } catch (e) {
    checks.database = { status: 'down', error: e.message };
  }

  // Check BSC RPC
  try {
    const rpcResp = await fetch(BSC_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'eth_blockNumber', params: [], id: 1 }),
      signal: AbortSignal.timeout(5000),
    });
    const rpcData = await rpcResp.json();
    checks.bsc_rpc = { status: 'ok', block_height: parseInt(rpcData.result, 16) };
  } catch (e) {
    checks.bsc_rpc = { status: 'down', error: e.message };
  }

  const allOk = Object.values(checks).every(c => c.status === 'ok');
  res.json({
    status: allOk ? 'healthy' : 'degraded',
    version: '2.2.0',
    timestamp: new Date().toISOString(),
    checks,
  });
});

app.get('/metrics', (req, res) => {
  res.set('Content-Type', 'text/plain; version=0.0.4');
  res.send(renderMetrics());
});

// ── OpenAPI spec endpoint ──
app.get('/api-docs', (req, res) => {
  const specPath = path.join(__dirname, '..', 'docs', 'openapi.json');
  res.sendFile(specPath);
});

app.get('/api/v1/config', (req, res) => {
  res.json({
    demoMode: DEMO_MODE,
    escrowAddress: getEscrowAddress() || null,
    depositPoolAddress: DEPOSIT_POOL_ADDRESS,
  });
});

// ── 启动 ─────────────────────────────────────────

async function start() {
  try {
    await setupRoutes();

    const SSL_CERT = process.env.SSL_CERT_PATH;
    const SSL_KEY = process.env.SSL_KEY_PATH;

    if (SSL_CERT && SSL_KEY) {
      // HTTPS mode — production recommended
      const fs = require('fs');
      const https = require('https');
      const cert = fs.readFileSync(SSL_CERT);
      const key = fs.readFileSync(SSL_KEY);
      https.createServer({ cert, key }, app).listen(PORT, () => {
        console.log(`CryptoMinds API running on https://localhost:${PORT}`);
        console.log(`[ssl] TLS enabled — cert: ${SSL_CERT}, key: ${SSL_KEY}`);
        console.log(`[db] SQLite 数据库已初始化`);
        const escrowAddr = getEscrowAddress();
        if (escrowAddr) {
          console.log(`[escrow] 合约地址: ${escrowAddr}`);
        } else {
          console.log('[escrow] 合约未部署');
        }
        if (DEMO_MODE) {
          console.log('[demo] Demo 模式已启用');
        }
      });
    } else {
      // HTTP mode — dev/demo only
      app.listen(PORT, () => {
        console.log(`CryptoMinds API running on http://localhost:${PORT}`);
        if (!DEMO_MODE) {
          console.warn('[security] ⚠️  HTTP mode — set SSL_CERT_PATH + SSL_KEY_PATH for HTTPS in production');
        }
        console.log(`[db] SQLite 数据库已初始化`);
        const escrowAddr = getEscrowAddress();
        if (escrowAddr) {
          console.log(`[escrow] 合约地址: ${escrowAddr}`);
        } else {
          console.log('[escrow] 合约未部署');
        }
        if (DEMO_MODE) {
          console.log('[demo] Demo 模式已启用');
        }
      });
    }
  } catch (err) {
    console.error('启动失败:', err);
    process.exit(1);
  }
}

start();
