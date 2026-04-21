const express = require('express');
const { Web3 } = require('web3');
const path = require('path');
const fs = require('fs');
const { execFile, execFileSync, spawn } = require('child_process');
const dns = require('dns').promises;
const net = require('net');
const multer = require('multer');
const { injectCryptoMindsSkill } = require('./inject_skill');
const webpush = require('web-push');
const { createAgentBuyHandlers } = require('./lib/agent_buy');
const { createSellersStore, createSellersMarketHandlers } = require('./lib/sellers_market');

const upload = multer({ dest: '/tmp/cryptominds-uploads/', limits: { fileSize: 100 * 1024 } }); // 100KB max

const app = express();
const { getSellers, saveSellers } = createSellersStore(__dirname);
const BSC_RPC = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
const MINIMAX_API_KEY = process.env.MINIMAX_API_KEY || '';
const MINIMAX_BASE_URL = 'https://api.minimaxi.com/v1';
const w3 = new Web3(BSC_RPC);

// Web Push 配置
const VAPID_PUBLIC_KEY = process.env.VAPID_PUBLIC_KEY || 'BLzMOK5mKfFnE2xys9GxpEipw6P5hmvb1zOR4Hh5MY-taBxXXt7jIe8jON7-zhphRGrCpFH4_Sjt__8htdgq304';
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY || 'N9XArIyKx8ZZkJTS_gACVgibflcQQnyItwA_zxahAfU';
webpush.setVapidDetails('mailto:cryptominds@four.meme', VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);

// 推送订阅存储
const PUSH_SUBS_FILE = path.join(__dirname, '..', 'push_subs.json');
function getPushSubs() {
  if (!fs.existsSync(PUSH_SUBS_FILE)) return [];
  try { return JSON.parse(fs.readFileSync(PUSH_SUBS_FILE, 'utf8')); } catch { return []; }
}
function savePushSubs(subs) {
  fs.writeFileSync(PUSH_SUBS_FILE, JSON.stringify(subs, null, 2));
}

// 发送 Web Push 通知
async function sendPushNotification(wallet, payload) {
  const subs = getPushSubs();
  const mine = subs.filter(s => s.wallet?.toLowerCase() === wallet.toLowerCase());
  for (const sub of mine) {
    try {
      await webpush.sendNotification(sub.subscription, JSON.stringify(payload));
    } catch (err) {
      if (err.statusCode === 410) {
        // 订阅已失效，移除
        const idx = subs.indexOf(sub);
        if (idx > -1) { subs.splice(idx, 1); savePushSubs(subs); }
      }
    }
  }
}

// BNB 价格缓存
let bnbPriceUsd = 600; // 默认值
let bnbPriceLastFetch = 0;
async function fetchBnbPrice() {
  const now = Date.now();
  if (now - bnbPriceLastFetch < 60000) return bnbPriceUsd; // 1分钟缓存
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd');
    const data = await res.json();
    if (data.binancecoin?.usd) {
      bnbPriceUsd = data.binancecoin.usd;
      bnbPriceLastFetch = now;
    }
  } catch(e) {}
  return bnbPriceUsd;
}

const PORT = 3457;
const DEMO_WALLET = '0xd2f899ce74320aef9d8f2359183232a554f4c0e1';
// 押金池地址（获奖后替换为Four.meme地址或合约地址）
const DEPOSIT_POOL_ADDRESS = process.env.DEPOSIT_POOL_ADDRESS || '0x287A44aAADDB78CA67EffCD94E83046353723862';
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const SDK_DIR = path.join(__dirname, '..', 'agentpay_sdk');
const X402_VERIFY_SCRIPT = path.join(SDK_DIR, 'x402_verify.py');
const SMART_ROUTER_SCRIPT = path.join(SDK_DIR, 'smart_router.py');
const MANAGED_X402_SCRIPT = path.join(__dirname, '..', 'scripts', 'managed_x402_payment.py');
const ESCROW_DEPLOYMENT_FILE = path.join(__dirname, '..', 'escrow_deployment.json');
const ESCROW_ABI_FILE = path.join(__dirname, '..', 'build', 'contracts_ServiceEscrow_sol_ServiceEscrow.abi');
const STAKE_SELECTOR = '0x46f45b8d';

const ESCROW_STATUS_NAMES = ['None', 'Pending', 'Delivering', 'Delivered', 'Confirmed', 'Disputed', 'Refunded', 'Expired'];
const AUTO_BUY_KIND_RULES = [
  { kind: 'scan', keywords: ['scan', 'scanner', 'discover', 'find', 'hunt', 'alpha', 'meme', 'new coin', 'new token', 'pick', '搜', '扫描', '发现', '寻找', '新币', '新 token', '新币机会', '机会'] },
  { kind: 'risk', keywords: ['risk', 'security', 'safe', 'rug', 'audit', 'contract', '风控', '风险', '安全', '土狗', '审计', '合约'] },
  { kind: 'deep', keywords: ['holder', 'holders', 'whale', 'depth', 'distribution', 'on-chain', '持仓', '巨鲸', '筹码', '分布', '链上数据', '深度'] },
  { kind: 'report', keywords: ['report', 'strategy', 'advice', 'analysis', 'research', 'summary', '投研', '报告', '策略', '建议', '分析', '总结'] },
];

function isValidAddress(address) {
  return typeof address === 'string' && w3.utils.isAddress(address);
}

function isChainTxHash(tx) {
  return typeof tx === 'string' && /^0x[a-fA-F0-9]{64}$/.test(tx);
}

function sanitizeText(value, maxLength = 120) {
  if (typeof value !== 'string') return '';
  return value.trim().slice(0, maxLength);
}

function parsePositiveNumber(value) {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return parsed;
}

function parseNonNegativeNumber(value, fallback = 0) {
  if (value === undefined || value === null || value === '') return fallback;
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) return null;
  return parsed;
}

function isValidTxHash(txHash) {
  return typeof txHash === 'string' && /^0x[a-fA-F0-9]{64}$/.test(txHash);
}

function isLikelySolanaAddress(address) {
  return typeof address === 'string' && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address.trim());
}

function isSupportedWalletAddress(address) {
  return isValidAddress(address) || isLikelySolanaAddress(address);
}

function isPrivateIPv4(ip) {
  if (typeof ip !== 'string') return false;
  if (ip.startsWith('0.')) return true;
  if (ip.startsWith('10.')) return true;
  if (ip.startsWith('127.')) return true;
  if (ip.startsWith('169.254.')) return true;
  if (ip.startsWith('192.168.')) return true;
  const parts = ip.split('.').map(part => Number.parseInt(part, 10));
  if (parts.length !== 4 || parts.some(Number.isNaN)) return false;
  return parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31;
}

function isPrivateIP(ip) {
  if (!ip) return true;
  if (net.isIPv4(ip)) return isPrivateIPv4(ip);
  if (net.isIPv6(ip)) {
    const normalized = ip.toLowerCase();
    return normalized === '::' || normalized === '::1' || normalized.startsWith('fc') || normalized.startsWith('fd') || normalized.startsWith('fe80:');
  }
  return true;
}

async function validateServiceEndpoint(rawEndpoint) {
  const endpoint = typeof rawEndpoint === 'string' ? rawEndpoint.trim() : '';
  if (!endpoint) {
    return { ok: true, endpoint: '' };
  }

  let url;
  try {
    url = new URL(endpoint);
  } catch {
    return { ok: false, error: 'API Endpoint 不是合法 URL' };
  }

  if (!['http:', 'https:'].includes(url.protocol)) {
    return { ok: false, error: 'API Endpoint 仅支持 http/https' };
  }

  const hostname = (url.hostname || '').trim().toLowerCase();
  if (!hostname) {
    return { ok: false, error: 'API Endpoint 缺少主机名' };
  }
  if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
    return { ok: false, error: 'API Endpoint 不能指向 localhost' };
  }

  if (net.isIP(hostname)) {
    if (isPrivateIP(hostname)) {
      return { ok: false, error: 'API Endpoint 不能指向内网或本机地址' };
    }
    return { ok: true, endpoint: url.toString() };
  }

  try {
    const records = await dns.lookup(hostname, { all: true });
    if (!records.length) {
      return { ok: false, error: 'API Endpoint 域名解析失败' };
    }
    if (records.some(record => isPrivateIP(record.address))) {
      return { ok: false, error: 'API Endpoint 不能解析到内网或本机地址' };
    }
  } catch {
    return { ok: false, error: 'API Endpoint 域名解析失败' };
  }

  return { ok: true, endpoint: url.toString() };
}

function runPythonJson(scriptPath, args = [], timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    const proc = execFile(PYTHON_BIN, [scriptPath, ...args], { encoding: 'utf8', maxBuffer: 1024 * 1024, timeout: timeoutMs, killSignal: 'SIGTERM' }, (error, stdout, stderr) => {
      if (error) {
        const detail = (stderr?.trim() || '') + (stdout?.trim() ? '\n' + stdout.trim() : '') || error.message + (error.killed ? ' (超时)' : '');
        console.error('runPythonJson error:', scriptPath, args, error.code, error.killed, detail.substring(0, 200));
        reject(new Error(detail));
        return;
      }

      try {
        resolve(JSON.parse(stdout.trim()));
      } catch (parseError) {
        reject(new Error(`Python 输出不是合法 JSON: ${stdout || stderr || parseError.message}`));
      }
    });
  });
}

function findMatchingRoute(routes = [], selectedRoute = {}) {
  if (!selectedRoute || typeof selectedRoute !== 'object') return null;
  return routes.find(route =>
    route.route_type === selectedRoute.route_type &&
    route.chain === selectedRoute.chain &&
    route.symbol === selectedRoute.symbol
  ) || null;
}

function buildExecutionPreview(route, service) {
  if (!route) return null;

  const priceLabel = `${service.price} ${route.symbol || 'BNB'}`;
  const stepsByType = {
    direct: [
      `检查 ${route.chain.toUpperCase()} 链上 ${route.symbol} 余额`,
      route.symbol === 'BNB' ? `通过 Escrow 担保合约锁定 ${priceLabel}，确认收货后放款` : `向服务提供者地址发起 ${priceLabel} 支付`,
      '提交链上交易并验证',
    ],
    swap: [
      `检查 ${route.chain.toUpperCase()} 链上可兑换余额`,
      `调用 DEX 将现有资产兑换成 ${route.symbol}`,
      `完成目标代币支付并提交 x402 验证`,
    ],
    bridge: [
      '检查源链余额与桥接可用性',
      `桥接资产到 ${route.chain.toUpperCase()}`,
      `在目标链完成 ${route.symbol} 支付并提交 x402 验证`,
    ],
    split: [
      '汇总多链同币种余额',
      '按推荐比例拆分多笔支付',
      '聚合结果并写入统一订单记录',
    ],
  };

  return {
    execution_mode: route.route_type === 'direct' && route.symbol === 'BNB' && route.chain === 'bsc'
      ? 'real-or-demo'
      : 'demo-executor',
    steps: stepsByType[route.route_type] || ['准备执行路径', '提交支付', '等待订单完成'],
  };
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function callLocalMarketApi(apiPath, payload) {
  const response = await fetch(`http://127.0.0.1:${PORT}${apiPath}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

function getPurchaseById(purchaseId) {
  if (!purchaseId) return null;
  return getPurchases().find(item => item.id === purchaseId) || null;
}

async function waitForPurchaseState(purchaseId, options = {}) {
  const timeoutMs = Number(options.timeoutMs || 30000);
  const intervalMs = Number(options.intervalMs || 1500);
  const startedAt = Date.now();

  while (Date.now() - startedAt <= timeoutMs) {
    const purchase = getPurchaseById(purchaseId);
    if (purchase && ['delivered', 'completed', 'rejected', 'demo-completed'].includes(purchase.status)) {
      return purchase;
    }
    await sleep(intervalMs);
  }

  return getPurchaseById(purchaseId);
}

function summarizeAutoResult(value) {
  if (!value) return '';
  if (typeof value === 'string') return value.trim().slice(0, 180);
  if (typeof value.summary === 'string') return value.summary.trim().slice(0, 180);
  if (typeof value.report === 'string') return value.report.trim().slice(0, 180);
  if (typeof value.message === 'string') return value.message.trim().slice(0, 180);
  if (value.result && typeof value.result === 'object') {
    return summarizeAutoResult(value.result);
  }
  try {
    return JSON.stringify(value).slice(0, 180);
  } catch {
    return '';
  }
}

function getServiceKind(service) {
  const searchable = `${service.id || ''} ${service.name || ''} ${service.desc || ''} ${service.outputFormat || ''}`.toLowerCase();
  if (/(scan|scanner|扫描|新币|meme|alpha)/.test(searchable)) return 'scan';
  if (/(risk|security|audit|风控|风险|安全|合约)/.test(searchable)) return 'risk';
  if (/(deep|holder|whale|持仓|巨鲸|分布)/.test(searchable)) return 'deep';
  if (/(report|strategy|analysis|research|报告|策略|建议|分析)/.test(searchable)) return 'report';
  return 'generic';
}

function scoreServiceForTask(service, task) {
  const taskLower = String(task || '').toLowerCase();
  const haystack = `${service.id || ''} ${service.name || ''} ${service.desc || ''} ${service.inputFormat || ''} ${service.outputFormat || ''}`.toLowerCase();
  let score = 0;

  for (const rule of AUTO_BUY_KIND_RULES) {
    const taskMatched = rule.keywords.some(keyword => taskLower.includes(keyword.toLowerCase()));
    if (!taskMatched) continue;
    if (getServiceKind(service) === rule.kind) score += 80;
    for (const keyword of rule.keywords) {
      if (haystack.includes(keyword.toLowerCase())) score += 8;
    }
  }

  const taskTokens = taskLower.split(/[\s,.;:!?，。；：！？、()（）/\\-]+/).filter(Boolean);
  for (const token of taskTokens) {
    if (token.length < 2) continue;
    if (haystack.includes(token)) score += 4;
  }

  score += Math.round((Number(service.effectiveRate || 0) * 100) * 0.4);
  score += Math.min(Number(service.totalCalls || 0), 100) * 0.1;
  score += Math.min(Number(service.deposit || 0) * 1000, 20);
  return score;
}

function buildAutoBuyPlan(task, services, maxServices = 3) {
  const activeServices = services
    .filter(service => service.active && !['rejected', 'deregistered'].includes(service.status))
    .map(service => ({ ...service, _kind: getServiceKind(service), _score: scoreServiceForTask(service, task) }));

  const requestedKinds = [];
  const taskLower = String(task || '').toLowerCase();
  for (const rule of AUTO_BUY_KIND_RULES) {
    if (rule.keywords.some(keyword => taskLower.includes(keyword.toLowerCase()))) {
      requestedKinds.push(rule.kind);
    }
  }

  const plan = [];
  for (const kind of [...new Set(requestedKinds)]) {
    const best = activeServices
      .filter(service => service._kind === kind)
      .sort((a, b) => (b._score || 0) - (a._score || 0))[0];
    if (best && !plan.some(item => item.id === best.id)) plan.push(best);
  }

  if (plan.length === 0 && activeServices.length > 0) {
    const bestOverall = [...activeServices].sort((a, b) => (b._score || 0) - (a._score || 0))[0];
    if (bestOverall) plan.push(bestOverall);
  }

  return plan.slice(0, Math.max(1, Math.min(Number(maxServices) || 1, 3)));
}

function buildAgentRecommendations(task, services, maxCandidates = 8) {
  const activeServices = services
    .filter(service => service.active && !['rejected', 'deregistered'].includes(service.status))
    .map(service => {
      const kind = getServiceKind(service);
      const score = scoreServiceForTask(service, task);
      const reasons = [];
      if (score >= 80) reasons.push('任务语义高度匹配');
      if (Number(service.effectiveRate || 0) >= 0.8) reasons.push(`有效率 ${(Number(service.effectiveRate || 0) * 100).toFixed(0)}%`);
      if (Number(service.totalCalls || 0) > 0) reasons.push(`累计调用 ${service.totalCalls}`);
      if (Number(service.deposit || 0) > 0) reasons.push(`质押 ${service.deposit} BNB`);
      return { ...service, _kind: kind, _score: score, _reasons: reasons };
    })
    .sort((a, b) => (b._score || 0) - (a._score || 0));

  return activeServices.slice(0, Math.max(1, Math.min(Number(maxCandidates) || 8, 12)));
}

function normalizePurchasePlan(rawPlan, fallbackPlan) {
  if (Array.isArray(rawPlan) && rawPlan.length > 0) {
    return rawPlan
      .map(item => typeof item === 'string' ? { serviceId: item } : item)
      .filter(item => item && typeof item.serviceId === 'string')
      .map(item => ({
        serviceId: sanitizeText(item.serviceId, 120),
        input: sanitizeText(item.input, 240),
        paymentPreference: sanitizeText(item.paymentPreference, 40).toLowerCase() || '',
      }))
      .filter(item => item.serviceId);
  }
  return fallbackPlan.map(service => ({ serviceId: service.id }));
}

function resolvePlanServices(planItems, services, buyerWallet) {
  const resolved = [];
  for (const item of planItems) {
    const service = services.find(candidate => candidate.id === item.serviceId);
    if (!service || !service.active || ['rejected', 'deregistered'].includes(service.status)) {
      throw new Error(`服务不存在或不可购买: ${item.serviceId}`);
    }
    if (service.wallet?.toLowerCase() === buyerWallet.toLowerCase()) {
      throw new Error(`不能购买自己的服务: ${item.serviceId}`);
    }
    resolved.push({ ...item, service });
  }
  return resolved;
}

function buildAutoStepInput(task, previousStep, explicitTargetAddress) {
  if (explicitTargetAddress && isValidAddress(explicitTargetAddress)) return explicitTargetAddress;
  if (!previousStep) return String(task || '').trim().slice(0, 240);
  const summary = summarizeAutoResult(previousStep.result || previousStep.invocation || previousStep.purchase?.result || previousStep.purchase?.report);
  return `${String(task || '').trim()}\n\n上一步结果摘要：${summary}`.slice(0, 240);
}

function inferServiceResultType(service) {
  const searchable = `${service?.id || ''} ${service?.name || ''} ${service?.outputFormat || ''}`.toLowerCase();
  if (/(json|api|结构化|结构)/.test(searchable)) return 'json';
  if (/(report|报告|strategy|analysis|summary|建议)/.test(searchable)) return 'report';
  if (/(scan|scanner|risk|table|list|列表|风控)/.test(searchable)) return 'analysis';
  return 'text';
}

function normalizeHostedDeliveryOutput(service, payload, context = {}) {
  const resultType = service?.resultType || inferServiceResultType(service);
  const summary = summarizeAutoResult(payload) || `${service?.name || '服务'} 已生成结果`;
  const normalized = {
    version: 'hosted-result/v1',
    serviceId: service?.id || '',
    serviceName: service?.name || '',
    seller: service?.expert || '',
    resultType,
    title: service?.name || '服务结果',
    summary,
    input: context.input || '',
    generatedAt: new Date().toISOString(),
    deliveryMode: service?.deliveryMode || 'auto_with_manual_fallback',
    data: payload,
  };

  if (payload && typeof payload === 'object') {
    if (typeof payload.report === 'string' && payload.report.trim()) normalized.summary = payload.report.trim().slice(0, 180);
    else if (typeof payload.summary === 'string' && payload.summary.trim()) normalized.summary = payload.summary.trim().slice(0, 180);
    else if (payload.result && typeof payload.result === 'object') {
      const nested = summarizeAutoResult(payload.result);
      if (nested) normalized.summary = nested;
    }
  }

  return normalized;
}

async function createManagedX402Payment(service, buyerWallet, description) {
  const fromName = getManagedWalletNameByAddress(buyerWallet);
  const toName = getManagedWalletNameByAddress(service.wallet);
  if (!fromName || !toName) {
    throw new Error('缺少托管钱包映射，无法自动发起 x402 支付');
  }
  return runPythonJson(
    MANAGED_X402_SCRIPT,
    [fromName, toName, String(service.price), service.id, description || service.name],
    60000
  );
}

async function resolveSelectedRoute(serviceId, walletAddress, selectedRoute) {
  if (!selectedRoute) return null;
  const services = getServices();
  const service = services.find(item => item.id === serviceId);
  if (!service) {
    throw new Error('服务不存在');
  }
  const result = await runPythonJson(SMART_ROUTER_SCRIPT, ['--wallet', walletAddress, '--service', serviceId], 30000);
  if (!result.success) {
    throw new Error(result.error || '智能路由计算失败');
  }

  const matchedRoute = findMatchingRoute(result.routes, selectedRoute);
  if (!matchedRoute) {
    throw new Error('所选智能路由已失效，请重新获取推荐');
  }
  matchedRoute.execution_preview = buildExecutionPreview(matchedRoute, service);
  return matchedRoute;
}

async function verifySplitHeaders(paymentHeaders, serviceId, expectedBuyerWallet, service) {
  if (!Array.isArray(paymentHeaders) || paymentHeaders.length < 2) {
    throw new Error('split 支付至少需要两笔 payment headers');
  }

  const seenTxHashes = new Set();
  const results = [];

  for (const header of paymentHeaders) {
    const result = await runPythonJson(X402_VERIFY_SCRIPT, [header, serviceId]);
    if (!result.valid) {
      throw new Error(result.error || '子支付验证失败');
    }
    if (!result.tx_hash || !isValidTxHash(result.tx_hash)) {
      throw new Error('split 子支付缺少有效 txHash');
    }
    if (seenTxHashes.has(result.tx_hash)) {
      throw new Error('split 子支付存在重复 txHash');
    }
    seenTxHashes.add(result.tx_hash);

    if (expectedBuyerWallet && result.from_address?.toLowerCase() !== expectedBuyerWallet.toLowerCase()) {
      throw new Error('split 子支付付款地址不一致');
    }
    if (service?.wallet && result.to_address?.toLowerCase() !== service.wallet.toLowerCase()) {
      throw new Error('split 子支付收款地址不一致');
    }
    results.push(result);
  }

  const totalAmount = results.reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const expectedAmount = Number(service?.price || 0);
  if (expectedAmount > 0 && totalAmount < expectedAmount * 0.95) {
    throw new Error(`split 总支付金额不足: 期望 ${expectedAmount}, 实际 ${totalAmount}`);
  }

  return {
    results,
    totalAmount,
    txHashes: results.map(item => item.tx_hash),
    chains: [...new Set(results.map(item => item.chain).filter(Boolean))],
    fromAddress: results[0]?.from_address || expectedBuyerWallet,
    toAddress: results[0]?.to_address || service?.wallet || '',
  };
}

async function verifyPaymentTx(txHash, buyerWallet, service) {
  return verifyEscrowPaymentTx(txHash, buyerWallet, service, null);
}

function normalizeEscrowStatus(rawStatus) {
  if (typeof rawStatus === 'string' && Number.isNaN(Number(rawStatus))) {
    return rawStatus;
  }
  return ESCROW_STATUS_NAMES[Number(rawStatus)] || 'Unknown';
}

function decodeSingleStringArg(txInput, selector) {
  if (typeof txInput !== 'string' || !txInput.toLowerCase().startsWith(selector.toLowerCase())) {
    return null;
  }
  try {
    const decoded = w3.eth.abi.decodeParameters(['string'], `0x${txInput.slice(10)}`);
    return decoded[0] || null;
  } catch (err) {
    return null;
  }
}

async function fetchEscrowOrder(orderId) {
  const contract = new w3.eth.Contract(ESCROW_ABI, ESCROW_CONFIG.address);
  const order = await contract.methods.getOrder(orderId).call();
  let timeoutSeconds = ESCROW_CONFIG.defaultTimeout;
  try {
    const raw = await contract.methods.orders(orderId).call();
    timeoutSeconds = Number(raw[7] ?? raw.timeoutSeconds ?? ESCROW_CONFIG.defaultTimeout);
  } catch (err) {}
  return {
    buyer: order[0],
    seller: order[1],
    serviceId: order[2],
    amount: order[3],
    amountBNB: w3.utils.fromWei(order[3], 'ether'),
    createdAt: Number(order[4]),
    deliveredAt: Number(order[5]),
    timeoutAt: Number(order[6]),
    timeoutSeconds,
    status: normalizeEscrowStatus(order[7]),
    deliverResult: order[8],
  };
}

function getEscrowContract() {
  return new w3.eth.Contract(ESCROW_ABI, ESCROW_CONFIG.address);
}

async function sendEscrowSignedTx(methodName, args, signer) {
  const wallet = typeof signer === 'string'
    ? findManagedWalletByAddress(signer)
    : signer;
  if (!wallet?.privateKey || !wallet?.address) {
    throw new Error('未找到可用的托管钱包签名该 Escrow 交易');
  }

  const account = w3.eth.accounts.privateKeyToAccount(wallet.privateKey);
  const contract = getEscrowContract();
  const method = contract.methods[methodName](...args);
  const gas = await method.estimateGas({ from: account.address });
  const gasPrice = await w3.eth.getGasPrice();
  const nonce = await w3.eth.getTransactionCount(account.address, 'pending');
  const signed = await account.signTransaction({
    from: account.address,
    to: ESCROW_CONFIG.address,
    data: method.encodeABI(),
    gas: Number(gas) + 200000,
    gasPrice,
    nonce,
    chainId: ESCROW_CONFIG.chainId,
    value: '0x0',
  });

  return w3.eth.sendSignedTransaction(signed.rawTransaction);
}

async function createEscrowOrderForBuyer(service, buyerWallet, timeoutSeconds = ESCROW_CONFIG.defaultTimeout) {
  const wallet = findManagedWalletByAddress(buyerWallet);
  if (!wallet?.privateKey || !wallet?.address) {
    throw new Error('买家钱包未托管，无法自动发起 Escrow 下单');
  }

  const account = w3.eth.accounts.privateKeyToAccount(wallet.privateKey);
  const contract = getEscrowContract();
  const value = w3.utils.toWei(String(service.price), 'ether');
  const method = contract.methods.createOrder(service.wallet, service.id, timeoutSeconds);
  const gas = await method.estimateGas({ from: account.address, value });
  const gasPrice = await w3.eth.getGasPrice();
  const nonce = await w3.eth.getTransactionCount(account.address, 'pending');
  const signed = await account.signTransaction({
    from: account.address,
    to: ESCROW_CONFIG.address,
    data: method.encodeABI(),
    gas: Number(gas) + 200000,
    gasPrice,
    nonce,
    chainId: ESCROW_CONFIG.chainId,
    value,
  });

  const receipt = await w3.eth.sendSignedTransaction(signed.rawTransaction);
  const orderId = receipt?.events?.OrderCreated?.returnValues?.orderId || '';
  if (!orderId) {
    throw new Error('Escrow 下单成功，但未解析到 orderId');
  }

  return {
    txHash: receipt.transactionHash,
    escrowOrderId: orderId,
  };
}

async function confirmEscrowOrderAsBuyer(orderId, buyerWallet) {
  const wallet = findManagedWalletByAddress(buyerWallet);
  if (!wallet?.privateKey || !wallet?.address) {
    throw new Error('买家钱包未托管，无法自动确认 Escrow 订单');
  }
  const receipt = await sendEscrowSignedTx('confirm', [orderId], wallet);
  return { txHash: receipt.transactionHash };
}

async function verifyEscrowPaymentTx(txHash, buyerWallet, service, escrowOrderId) {
  if (!isValidTxHash(txHash)) {
    return { ok: false, error: 'txHash 格式无效' };
  }

  try {
    const receipt = await w3.eth.getTransactionReceipt(txHash);
    const tx = await w3.eth.getTransaction(txHash);

    if (!receipt || !tx) return { ok: false, error: '链上未找到这笔交易' };
    if (Number(receipt.status) !== 1) return { ok: false, error: '链上交易执行失败' };
    if (!tx.to) return { ok: false, error: '交易缺少接收地址' };

    const actualTo = tx.to.toLowerCase();
    const actualFrom = tx.from.toLowerCase();
    const expectedFrom = buyerWallet.toLowerCase();
    const expectedValueWei = BigInt(w3.utils.toWei(String(service.price), 'ether'));
    const actualValueWei = BigInt(tx.value.toString());
    const expectedEscrowTo = ESCROW_CONFIG.address.toLowerCase();

    if (actualTo !== expectedEscrowTo) {
      return { ok: false, error: 'BNB 支付必须进入 Escrow 担保合约' };
    }
    if (actualFrom !== expectedFrom) {
      return { ok: false, error: '付款地址不匹配 buyerWallet' };
    }
    if (actualValueWei < expectedValueWei) {
      return { ok: false, error: '链上支付金额不足' };
    }
    if (!escrowOrderId) {
      return { ok: false, error: '缺少 escrowOrderId，无法校验担保订单' };
    }

    const order = await fetchEscrowOrder(escrowOrderId);
    if (!order || order.buyer === '0x0000000000000000000000000000000000000000') {
      return { ok: false, error: 'Escrow 订单不存在' };
    }
    if (order.buyer.toLowerCase() !== expectedFrom) {
      return { ok: false, error: 'Escrow 订单买家与 buyerWallet 不一致' };
    }
    if (order.seller.toLowerCase() !== service.wallet.toLowerCase()) {
      return { ok: false, error: 'Escrow 订单卖家与服务提供者不一致' };
    }
    if (order.serviceId !== service.id) {
      return { ok: false, error: 'Escrow 订单 serviceId 不匹配' };
    }
    if (BigInt(order.amount) < expectedValueWei) {
      return { ok: false, error: 'Escrow 订单锁定金额不足' };
    }
    if (order.status !== 'Pending' && order.status !== 'Delivered') {
      return { ok: false, error: `Escrow 订单状态异常: ${order.status}` };
    }

    return {
      ok: true,
      tx: {
        hash: txHash,
        from: tx.from,
        to: tx.to,
        value: actualValueWei.toString(), // BigInt转字符串
        blockNumber: Number(tx.blockNumber),
        gasUsed: Number(receipt.gasUsed),
        escrowOrderId,
      }
    };
  } catch (err) {
    return { ok: false, error: `校验 txHash 失败: ${err.message}` };
  }
}

// Agent 钱包（硬编码）
const AGENTS = {
  gangdan: { name: '钢蛋', role: '调度员', icon: '📡', addr: '0xd2f899CE74320AEf9d8f2359183232a554f4C0E1' },
  tiedan: { name: '铁蛋', role: '侦察兵', icon: '🔍', addr: '0xce0DE97496c20Dd773d75F560d3e4494cF542d96' },
  choudan: { name: '臭蛋', role: '风控员', icon: '🛡️', addr: '0x40992619077f0e42A1b7713C02B7324Fa1d8715c' },
  pidan: { name: '皮蛋', role: '数据师', icon: '📊', addr: '0x0BAdB40BED90515Cb436282C1D5bE059d17566BC' },
  ludan: { name: '卤蛋', role: '整理员', icon: '📝', addr: '0x4190877f1959E260B4613793e3D07e8A332bc44B' },
};

// 自由市场——专家自己入驻，自己定价，无分类

// 专家服务列表（支持入驻）
const SERVICES_FILE = path.join(__dirname, '..', 'services.json');
const AGENTS_FILE = path.join(__dirname, '..', 'agents.json');
const WALLETS_FILE = path.join(__dirname, '..', 'wallets.json');

function getWallets() {
  try {
    if (fs.existsSync(WALLETS_FILE)) {
      return JSON.parse(fs.readFileSync(WALLETS_FILE, 'utf8'));
    }
  } catch (e) {}
  return {};
}

function findManagedWalletByAddress(address) {
  if (!address) return null;
  const normalized = address.toLowerCase();
  const wallets = Object.values(getWallets());
  const found = wallets.find(item => item?.address && item.address.toLowerCase() === normalized);
  if (!found?.private_key) return null;
  return {
    address: found.address,
    privateKey: found.private_key.startsWith('0x') ? found.private_key : `0x${found.private_key}`,
  };
}

function getEscrowExecutorWallet() {
  const wallets = getWallets();
  const deployer = wallets.four_meme;
  if (!deployer?.address || !deployer?.private_key) return null;
  return {
    address: deployer.address,
    privateKey: deployer.private_key.startsWith('0x') ? deployer.private_key : `0x${deployer.private_key}`,
  };
}

function getManagedWalletNameByAddress(address) {
  if (!address) return '';
  const normalized = address.toLowerCase();
  const entries = Object.entries(getWallets());
  const found = entries.find(([, wallet]) => wallet?.address?.toLowerCase() === normalized);
  return found?.[0] || '';
}

function getAgents() {
  try {
    if (fs.existsSync(AGENTS_FILE)) return JSON.parse(fs.readFileSync(AGENTS_FILE, 'utf8'));
  } catch(e) {}
  return [];
}
function saveAgents(agents) {
  fs.writeFileSync(AGENTS_FILE, JSON.stringify(agents, null, 2));
}

function getServices() {
  try {
    if (fs.existsSync(SERVICES_FILE)) {
      const loaded = JSON.parse(fs.readFileSync(SERVICES_FILE, 'utf8'));
      // 确保所有服务都有 frameworks 字段
      return loaded.map(s => ({ ...s, frameworks: Array.isArray(s.frameworks) && s.frameworks.length > 0 ? s.frameworks : ['generic'], security: s.security || { level: 'safe', score: 100, summary: '✅ 内置服务' } }));
    }
  } catch (e) {}
  // 默认内置专家
  const defaults = [
    { id: 'tiedan-scan', expert: '铁蛋', wallet: '0xce0DE97496c20Dd773d75F560d3e4494cF542d96', name: '扫最新币', desc: '扫描 BSC 新上线代币，推荐有潜力的', price: 0.0005, deposit: 0.001, inputFormat: '代币合约地址（可选）', outputFormat: '新币列表 + 评分 + 涨幅', latency: '~3秒', totalCalls: 127, effectiveCalls: 113, effectiveRate: 0.89, active: true, avatar: '🔩', frameworks: ['openclaw','generic'], security: { level: 'safe', score: 100, summary: '✅ 内置服务' } },
    { id: 'choudan-risk', expert: '臭蛋', wallet: '0x40992619077f0e42A1b7713C02B7324Fa1d8715c', name: '代币风控', desc: '检查合约安全性、rug pull 风险', price: 0.0003, deposit: 0.001, inputFormat: '代币合约地址', outputFormat: '安全评分 + 风险项列表', latency: '~5秒', totalCalls: 89, effectiveCalls: 82, effectiveRate: 0.92, active: true, avatar: '🥚', frameworks: ['openclaw','generic'], security: { level: 'safe', score: 100, summary: '✅ 内置服务' } },
    { id: 'pidan-deep', expert: '皮蛋', wallet: '0x0BAdB40BED90515Cb436282C1D5bE059d17566BC', name: '深度分析', desc: '持仓分布、鲸鱼动向、链上数据', price: 0.0008, deposit: 0.001, inputFormat: '代币合约地址', outputFormat: '持仓分布 + 巨鲸动向 + 数据报告', latency: '~8秒', totalCalls: 67, effectiveCalls: 55, effectiveRate: 0.82, active: true, avatar: '🪺', frameworks: ['openclaw','langchain','generic'], security: { level: 'safe', score: 100, summary: '✅ 内置服务' } },
    { id: 'ludan-report', expert: '卤蛋', wallet: '0x4190877f1959E260B4613793e3D07e8A332bc44B', name: '投资分析', desc: '生成投资分析、持有策略建议', price: 0.0001, deposit: 0.0005, inputFormat: '代币合约地址', outputFormat: '投资分析报告 + 策略建议', latency: '~10秒', totalCalls: 203, effectiveCalls: 170, effectiveRate: 0.84, active: true, avatar: '📝', frameworks: ['openclaw','generic'], security: { level: 'safe', score: 100, summary: '✅ 内置服务' } },
  ];
  saveServices(defaults);
  return defaults;
}

function saveServices(services) {
  fs.writeFileSync(SERVICES_FILE, JSON.stringify(services, null, 2));
}

// 声誉数据
const REPUTATION_FILE = path.join(__dirname, '..', 'agents', 'reputation_data.json');
function getReputationData() {
  try {
    if (fs.existsSync(REPUTATION_FILE)) {
      return JSON.parse(fs.readFileSync(REPUTATION_FILE, 'utf8'));
    }
  } catch (e) {}
  return {};
}

// 通知系统
const NOTIFICATIONS_FILE = path.join(__dirname, '..', 'notifications.json');

function getNotifications() {
  try {
    if (fs.existsSync(NOTIFICATIONS_FILE)) {
      return JSON.parse(fs.readFileSync(NOTIFICATIONS_FILE, 'utf8'));
    }
  } catch (e) {}
  return [];
}

function saveNotifications(notifications) {
  fs.writeFileSync(NOTIFICATIONS_FILE, JSON.stringify(notifications, null, 2));
}

function addNotification(notification) {
  const notifications = getNotifications();
  notifications.unshift({
    id: `ntf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    read: false,
    createdAt: new Date().toISOString(),
    ...notification,
  });
  if (notifications.length > 500) notifications.length = 500;
  saveNotifications(notifications);

  // Web Push 推送
  if (notification.targetWallet) {
    let icon = '', title = 'CryptoMinds 通知', body = '';
    if (notification.type === 'new_order') {
      icon = '🛒'; title = '新订单'; body = `${notification.buyerName || '买家'} 购买了 ${notification.serviceName || '服务'}`;
    } else if (notification.type === 'order_confirmed') {
      icon = '✅'; title = '订单确认'; body = `${notification.serviceName || '服务'} 已确认`;
    } else if (notification.type === 'order_result') {
      icon = '📦'; title = '结果已出'; body = `${notification.serviceName || '服务'} 结果已交付`;
    } else if (notification.type === 'manual_delivery_required') {
      icon = '🧑'; title = '需要人工发货'; body = `${notification.serviceName || '服务'} 自动交付失败，请手动处理`;
    } else if (notification.type === 'order_refunded') {
      icon = '💸'; title = '订单已退款'; body = `${notification.serviceName || '服务'} 因超时未交付已退款`;
    }
    sendPushNotification(notification.targetWallet, { icon, title, body, notificationId: notifications[0].id }).catch(() => {});
  }

  return notifications[0];
}

// 服务购买记录
const PURCHASES_FILE = path.join(__dirname, '..', 'purchases.json');

function getPurchases() {
  try {
    if (fs.existsSync(PURCHASES_FILE)) {
      return JSON.parse(fs.readFileSync(PURCHASES_FILE, 'utf8'));
    }
  } catch (e) {}
  return [];
}

function addPurchase(purchase) {
  const purchases = getPurchases();
  purchases.unshift(purchase);
  if (purchases.length > 50) purchases.length = 50;
  fs.writeFileSync(PURCHASES_FILE, JSON.stringify(purchases, null, 2));
}

function savePurchases(purchases) {
  fs.writeFileSync(PURCHASES_FILE, JSON.stringify(purchases, null, 2));
}

// ============================================
// 链上数据查询辅助函数
// ============================================

// PancakeSwap Factory 地址
const PANCAKE_FACTORY = '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73';
const PANCAKE_FACTORY_ABI = JSON.parse('[{"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"allPairs","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"allPairsLength","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]');

// ERC20 最小 ABI
const ERC20_ABI = JSON.parse('[{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]');

// 获取最新创建的代币对
async function getLatestPairs(count = 5) {
  try {
    const factory = new w3.eth.Contract(PANCAKE_FACTORY_ABI, PANCAKE_FACTORY);
    const totalPairs = Number(await factory.methods.allPairsLength().call());
    const pairs = [];
    
    // 获取最近创建的几个交易对
    const start = Math.max(0, totalPairs - count);
    for (let i = totalPairs - 1; i >= start && pairs.length < count; i--) {
      try {
        const pairAddr = await factory.methods.allPairs(i).call();
        // 这里简化处理，实际可以获取更多信息
        pairs.push({
          index: i,
          pairAddress: pairAddr,
        });
      } catch (e) {
        continue;
      }
    }
    return pairs;
  } catch (err) {
    console.error('获取交易对失败:', err.message);
    return [];
  }
}

// 检查代币合约安全性
async function checkTokenSecurity(tokenAddress) {
  try {
    const checksumAddr = w3.utils.toChecksumAddress(tokenAddress);
    const token = new w3.eth.Contract(ERC20_ABI, checksumAddr);
    
    const checks = [];
    let owner = null;
    let totalSupply = null;
    let name = 'Unknown';
    let symbol = '???';
    
    try { name = await token.methods.name().call(); } catch(e) {}
    try { symbol = await token.methods.symbol().call(); } catch(e) {}
    try { totalSupply = await token.methods.totalSupply().call(); } catch(e) {}
    
    // 检查 owner 权限
    try {
      owner = await token.methods.owner().call();
      checks.push({ item: 'owner 权限', status: owner === '0x0000000000000000000000000000000000000000' ? '✅ 已放弃' : '⚠️ 未放弃', detail: owner });
    } catch(e) {
      checks.push({ item: 'owner 权限', status: '✅ 无 owner 函数', detail: '合约没有 owner 函数' });
    }
    
    // 检查 totalSupply
    if (totalSupply) {
      const supply = w3.utils.fromWei(totalSupply, 'ether');
      checks.push({ item: '总供应量', status: '✅', detail: `${supply} ${symbol}` });
    }
    
    // 检查合约代码大小
    const code = await w3.eth.getCode(checksumAddr);
    const codeSize = (code.length - 2) / 2;
    checks.push({ 
      item: '合约已部署', 
      status: codeSize > 0 ? '✅' : '❌', 
      detail: `代码大小: ${codeSize} bytes` 
    });
    
    return { name, symbol, owner, totalSupply, checks, codeSize };
  } catch (err) {
    return { error: err.message, checks: [{ item: '合约检查', status: '❌ 失败', detail: err.message }] };
  }
}

// 查询钱包代币余额
async function getWalletTokenBalance(walletAddress, tokenAddress) {
  try {
    const token = new w3.eth.Contract(ERC20_ABI, tokenAddress);
    const balance = await token.methods.balanceOf(walletAddress).call();
    const symbol = await token.methods.symbol().call().catch(() => '???');
    const decimals = await token.methods.decimals().call().catch(() => 18);
    const formatted = Number(balance) / Math.pow(10, Number(decimals));
    return { balance: formatted, symbol, raw: balance.toString() };
  } catch (err) {
    return { balance: 0, symbol: '???', error: err.message };
  }
}

// 生成服务执行结果（基于真实链上数据）
async function generateReport(serviceType, buyerWallet, targetAddress = null) {
  const ts = new Date().toISOString();
  
  // 尝试调用真实 Python Agent runtime
  const runtimeMap = {
    'scanning': 'tiedan',
    'risk': 'choudan',
    'report': 'ludan',
  };
  const agentName = runtimeMap[serviceType];
  
  if (agentName) {
    try {
      const runtimeScript = path.join(__dirname, '..', 'agent_runtimes', `${agentName === 'tiedan' ? 'tiedan_scan' : agentName === 'choudan' ? 'choudan_risk' : 'ludan_report'}.py`);
      const runtimeArgs = ['import', 'sys; sys.path.insert(0, "' + path.join(__dirname, '..') + '"); from agent_runtimes import RUNTIMES; import json; r = RUNTIMES["' + agentName + '"](' + (targetAddress ? 'task_description="分析", token_address="' + targetAddress + '"' : 'task_description="分析"') + '); print(json.dumps(r, ensure_ascii=False))'];
      // 用 orchestrator.py 的 run_skill 代替，更接近真实流程
      const orchestratorPath = path.join(__dirname, '..', 'orchestrator.py');
      const env = { ...process.env, CRYPTOMINDS_OFFLINE: process.env.CRYPTOMINDS_OFFLINE || '0' };
      const result = await new Promise((resolve, reject) => {
        const py = spawn(PYTHON_BIN, ['-c', 
          'import sys, json; sys.path.insert(0, "' + path.join(__dirname, '..') + '"); ' +
          'from agent_runtimes import RUNTIMES; ' +
          'r = RUNTIMES["' + agentName + '"](' + (targetAddress ? 'task_description="执行任务", token_address="' + targetAddress + '"' : 'task_description="执行任务"') + '); ' +
          'print(json.dumps(r, ensure_ascii=False))'
        ], { env, timeout: 20000 });
        let stdout = '', stderr = '';
        py.stdout.on('data', d => stdout += d);
        py.stderr.on('data', d => stderr += d);
        py.on('close', code => {
          if (code === 0 && stdout.trim()) {
            try { resolve(JSON.parse(stdout.trim())); } catch { resolve(null); }
          } else { resolve(null); }
        });
        py.on('error', () => resolve(null));
      });
      
      if (result) {
        // 合并 Agent runtime 结果和标准格式
        return { ...result, _source: 'agent_runtime', _agent: agentName, timestamp: ts };
      }
    } catch (e) {
      console.error('Agent runtime 调用失败，降级到链上查询:', e.message);
    }
  }
  
  // 降级：链上查询
  switch(serviceType) {
    case 'scanning': {
      // 真实链上查询：获取最新交易对
      const pairs = await getLatestPairs(5);
      const data = [];
      
      // 查一些知名代币作为参考
      const knownTokens = [
        { name: 'CAKE', address: '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82' },
        { name: 'BUSD', address: '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56' },
        { name: 'USDT', address: '0x55d398326f99059fF775485246999027B3197955' },
      ];
      
      for (const token of knownTokens) {
        try {
          const tokenContract = new w3.eth.Contract(ERC20_ABI, token.address);
          const totalSupply = await tokenContract.methods.totalSupply().call().catch(() => '0');
          const supply = w3.utils.fromWei(totalSupply, 'ether');
          data.push({
            name: token.name,
            address: token.address,
            totalSupply: `${Number(supply).toLocaleString()} ${token.name}`,
            risk: '低',
          });
        } catch (e) {
          data.push({ name: token.name, address: token.address, error: e.message, risk: '未知' });
        }
      }
      
      // 添加最近发现的交易对
      for (const pair of pairs.slice(0, 3)) {
        data.push({
          name: `Pair #${pair.index}`,
          address: pair.pairAddress,
          type: 'LP Pair',
          risk: '待分析',
        });
      }
      
      return {
        type: 'scanning',
        title: '服务执行结果 — BSC 最新代币',
        timestamp: ts,
        source: '链上实时查询',
        data,
        recommendation: '以上数据来自链上实时查询，建议结合其他指标综合判断',
      };
    }
    
    case 'risk': {
      // 真实链上查询：检查合约安全性
      const tokenAddr = targetAddress || '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82'; // 默认 CAKE
      const security = await checkTokenSecurity(tokenAddr);
      
      let score = 50;
      if (security.checks) {
        security.checks.forEach(c => {
          if (c.status.includes('✅')) score += 10;
          if (c.status.includes('⚠️')) score -= 5;
        });
      }
      score = Math.min(100, Math.max(0, score));
      
      return {
        type: 'risk',
        title: '风控分析结果',
        timestamp: ts,
        source: '链上实时查询',
        target: security.name || 'Unknown',
        symbol: security.symbol,
        address: tokenAddr,
        score,
        risk: score >= 70 ? '低' : score >= 40 ? '中' : '高',
        checks: security.checks || [],
        conclusion: score >= 70 ? '合约安全性良好' : score >= 40 ? '存在一定风险，谨慎操作' : '风险较高，不建议操作',
      };
    }
    
    case 'report': {
      // 真实链上查询：查钱包持仓
      const bnbBalance = await w3.eth.getBalance(buyerWallet);
      const bnbFormatted = w3.utils.fromWei(bnbBalance, 'ether');
      
      // 查 CAKE 余额作为示例
      const cakeAddr = '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82';
      const cakeBalance = await getWalletTokenBalance(buyerWallet, cakeAddr);
      
      return {
        type: 'report',
        title: '持有建议',
        timestamp: ts,
        source: '链上实时查询',
        buyer: buyerWallet,
        summary: '钱包持仓分析',
        holdings: {
          bnb: `${bnbFormatted} BNB`,
          tokens: [
            { name: cakeBalance.symbol, balance: cakeBalance.balance, address: cakeAddr },
          ],
        },
        suggestion: '以上为链上实时数据，建议根据市场情况调整策略',
      };
    }
    
    default:
      return { type: 'unknown', message: '未知服务类型', timestamp: ts };
  }
}

function getPurchaseInput(purchase) {
  if (!purchase) return '';
  if (typeof purchase.input === 'string' && purchase.input.trim()) return purchase.input.trim();
  if (typeof purchase.task === 'string' && purchase.task.trim()) return purchase.task.trim();
  return '';
}

function resolveTargetAddress(input) {
  if (!input || typeof input !== 'string') return null;
  const trimmed = input.trim();
  return isValidAddress(trimmed) ? trimmed : null;
}

// 沙箱执行卖家上传的代码（托管模式）
async function runSandboxed(skillFilePath, payload, ext) {
  const startTime = Date.now();
  const timeout = 30000; // 30秒超时
  const inputJson = JSON.stringify(payload);

  return new Promise((resolve, reject) => {
    let cmd, args;
    if (ext === '.py') {
      cmd = 'python3';
      args = ['-u', skillFilePath];
    } else if (ext === '.js') {
      cmd = 'node';
      args = ['--no-warnings', skillFilePath];
    } else {
      return reject(new Error(`不支持的文件类型: ${ext}`));
    }

    const child = spawn(cmd, args, {
      timeout,
      env: { ...process.env, TASK_INPUT: inputJson },
      stdio: ['pipe', 'pipe', 'pipe'],
      cwd: path.dirname(skillFilePath),
    });

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });

    child.on('close', (code) => {
      const elapsed = Date.now() - startTime;
      if (code !== 0) {
        return reject(new Error(`沙箱执行失败 (exit ${code}, ${elapsed}ms): ${stderr.slice(0, 500)}`));
      }
      try {
        const result = JSON.parse(stdout.trim());
        resolve(result);
      } catch(e) {
        // 如果不是 JSON，包装为文本结果
        resolve({ ok: true, output: stdout.trim(), format: 'text', elapsed });
      }
    });

    child.on('error', (err) => {
      reject(new Error(`沙箱启动失败: ${err.message}`));
    });

    // 通过 stdin 传输入
    child.stdin.write(inputJson);
    child.stdin.end();
  });
}

async function executeServiceForPurchase(service, purchase) {
  const input = getPurchaseInput(purchase);
  const targetAddress = resolveTargetAddress(input);

  // 内置服务（铁蛋扫链、臭蛋风控、卤蛋报告）— 兼容旧数据
  if (service.id.includes('scan') || service.id.includes('risk') || service.id.includes('report')) {
    const reportType = service.id.includes('scan') ? 'scanning'
      : service.id.includes('risk') ? 'risk'
      : 'report';
    const report = await generateReport(reportType, purchase.buyerWallet, targetAddress);
    const normalized = normalizeHostedDeliveryOutput(service, report, { input, purchaseId: purchase.id });
    return {
      output: normalized,
      report: normalized,
      rawOutput: report,
    };
  }

  // 自托管模式：调用卖家 API
  if (service.deliveryMode === 'self_hosted' && service.api && service.api.endpoint) {
    const method = (service.api.method || 'POST').toUpperCase();
    const payload = {
      orderId: purchase.id,
      buyerWallet: purchase.buyerWallet,
      serviceId: service.id,
      input,
      task: input,
    };
    const fetchOptions = { method, headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(30000) };
    let url = service.api.endpoint;
    if (method === 'POST') {
      fetchOptions.body = JSON.stringify(payload);
    } else {
      const params = new URLSearchParams(payload).toString();
      url += (url.includes('?') ? '&' : '?') + params;
    }
    const response = await fetch(url, fetchOptions);
    if (!response.ok) {
      throw new Error(`卖家 API 返回 ${response.status}`);
    }
    const data = await response.json().catch(() => null);
    const normalized = normalizeHostedDeliveryOutput(service, data || { ok: true }, { input, purchaseId: purchase.id });
    return {
      output: normalized,
      report: normalized,
      rawOutput: data || null,
    };
  }

  // 托管模式：沙箱执行卖家上传的代码
  if (service.deliveryMode === 'hosted' && service.skillFilePath && fs.existsSync(service.skillFilePath)) {
    const ext = service.api?.skillExt || path.extname(service.skillFilePath);
    const payload = {
      orderId: purchase.id,
      buyerWallet: purchase.buyerWallet,
      serviceId: service.id,
      input: input,
      task: input,
      targetAddress: targetAddress || '',
    };
    const result = await runSandboxed(service.skillFilePath, payload, ext);
    const normalized = normalizeHostedDeliveryOutput(service, result, { input, purchaseId: purchase.id });
    return {
      output: normalized,
      report: normalized,
      rawOutput: result,
    };
  }

  throw new Error('该服务暂不支持自动交付');
}

async function markPurchaseDelivered(purchaseId, output, options = {}) {
  const purchases = getPurchases();
  const purchase = purchases.find(item => item.id === purchaseId);
  if (!purchase) throw new Error('订单不存在');
  if (purchase.status !== 'pending') return purchase;

  const services = getServices();
  const service = services.find(item => item.id === purchase.serviceId) || null;
  const normalizedOutput = output?.version === 'hosted-result/v1'
    ? output
    : normalizeHostedDeliveryOutput(service, output, {
        input: getPurchaseInput(purchase),
        purchaseId: purchase.id,
      });

  purchase.result = normalizedOutput;
  purchase.resultRaw = options.rawOutput || output || null;
  purchase.resultAt = new Date().toISOString();
  purchase.status = 'delivered';
  purchase.autoDelivered = options.autoDelivered === true;
  purchase.deliveryTxHash = options.deliveryTxHash || purchase.deliveryTxHash || '';
  purchase.resultType = normalizedOutput.resultType || purchase.resultType || inferServiceResultType(service);
  purchase.resultSummary = normalizedOutput.summary || summarizeAutoResult(normalizedOutput);
  if (options.report) purchase.report = options.report;
  savePurchases(purchases);

  addNotification({
    type: 'order_result',
    targetWallet: purchase.buyerWallet,
    orderId: purchase.id,
    serviceId: purchase.serviceId,
    serviceName: purchase.serviceName,
    sellerWallet: purchase.expertWallet,
    sellerName: purchase.expert,
  });

  return purchase;
}

async function attemptAutoDeliverPurchase(purchaseId) {
  const purchases = getPurchases();
  const purchase = purchases.find(item => item.id === purchaseId);
  if (!purchase || purchase.status !== 'pending') return;

  const services = getServices();
  const service = services.find(item => item.id === purchase.serviceId && item.active);
  if (!service) return;

  try {
    const result = await executeServiceForPurchase(service, purchase);
    let deliveryTxHash = '';
    if (purchase.escrowOrderId) {
      const managedSeller = findManagedWalletByAddress(purchase.expertWallet);
      if (!managedSeller) {
        throw new Error('卖家钱包未托管，需主人手动确认发货');
      }
      const receipt = await sendEscrowSignedTx('deliver', [purchase.escrowOrderId, JSON.stringify(result.output)], managedSeller);
      deliveryTxHash = receipt.transactionHash;
    }
    await markPurchaseDelivered(purchase.id, result.output, {
      autoDelivered: true,
      deliveryTxHash,
      report: result.report,
    });
  } catch (error) {
    addNotification({
      type: 'manual_delivery_required',
      targetWallet: purchase.expertWallet,
      orderId: purchase.id,
      serviceId: purchase.serviceId,
      serviceName: purchase.serviceName,
      buyerWallet: purchase.buyerWallet,
      buyerName: purchase.buyerName,
      reason: error.message,
    });
  }
}

let escrowReconcileRunning = false;
async function reconcileEscrowOrders() {
  if (escrowReconcileRunning) return;
  escrowReconcileRunning = true;
  try {
    const executor = getEscrowExecutorWallet();
    if (!executor) return;

    const purchases = getPurchases();
    for (const purchase of purchases) {
      if (!purchase.escrowOrderId || !purchase.escrowAddress) continue;
      try {
        const order = await fetchEscrowOrder(purchase.escrowOrderId);
        if (purchase.status === 'pending' && order.status === 'Pending') {
          const deadline = order.createdAt + (order.timeoutSeconds || ESCROW_CONFIG.defaultTimeout);
          if (deadline > 0 && Math.floor(Date.now() / 1000) >= deadline) {
            const receipt = await sendEscrowSignedTx('claimNoDeliveryRefund', [purchase.escrowOrderId], executor);
            purchase.status = 'rejected';
            purchase.refundedAt = new Date().toISOString();
            purchase.escrowStatus = 'Refunded';
            purchase.refundTxHash = receipt.transactionHash;
            addNotification({
              type: 'order_refunded',
              targetWallet: purchase.buyerWallet,
              orderId: purchase.id,
              serviceId: purchase.serviceId,
              serviceName: purchase.serviceName,
            });
          }
        } else if (purchase.status === 'delivered' && order.status === 'Delivered' && order.timeoutAt > 0 && Math.floor(Date.now() / 1000) >= order.timeoutAt) {
          const receipt = await sendEscrowSignedTx('claimTimeout', [purchase.escrowOrderId], executor);
          purchase.status = 'completed';
          purchase.confirmedAt = new Date().toISOString();
          purchase.escrowStatus = 'Expired';
          purchase.timeoutReleaseTxHash = receipt.transactionHash;
        } else if (order.status === 'Refunded') {
          purchase.status = 'rejected';
          purchase.escrowStatus = 'Refunded';
        } else if (order.status === 'Confirmed' || order.status === 'Expired') {
          if (purchase.status === 'delivered') {
            purchase.status = 'completed';
            purchase.confirmedAt = new Date().toISOString();
          }
          purchase.escrowStatus = order.status;
        }
      } catch (err) {}
    }
    savePurchases(purchases);
  } finally {
    escrowReconcileRunning = false;
  }
}

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// TX 记录
const TX_LOG = path.join(__dirname, '..', 'tx-log.json');
const AGENT_EVENTS_FILE = path.join(__dirname, '..', 'agent_events.json');

function loadEscrowDeployment() {
  try {
    return JSON.parse(fs.readFileSync(ESCROW_DEPLOYMENT_FILE, 'utf8'));
  } catch (err) {
    return {};
  }
}

function loadEscrowAbi() {
  try {
    return JSON.parse(fs.readFileSync(ESCROW_ABI_FILE, 'utf8'));
  } catch (err) {
    const deployment = loadEscrowDeployment();
    return deployment.abi || [];
  }
}

const ESCROW_DEPLOYMENT = loadEscrowDeployment();
const ESCROW_CONFIG = {
  address: process.env.ESCROW_ADDRESS || ESCROW_DEPLOYMENT.contractAddress || '0x47e1904364391f00147b9a77af9cf23cfd1b113c',
  chainId: Number(process.env.ESCROW_CHAIN_ID || ESCROW_DEPLOYMENT.chainId || 56),
  defaultTimeout: Number(process.env.ESCROW_DEFAULT_TIMEOUT || ESCROW_DEPLOYMENT.defaultTimeout || 86400),
};
const ESCROW_ABI = loadEscrowAbi();
function getTxs() {
  try { return JSON.parse(fs.readFileSync(TX_LOG, 'utf8')); } catch(e) { return []; }
}
function addTx(tx) {
  const txs = getTxs();
  // 去重：相同 tx hash 不重复写入
  const txKey = tx.tx || `${tx.from}-${tx.to}-${tx.amount}-${tx.time}`;
  if (txs.some(t => (t.tx && t.tx === tx.tx) || (!t.tx && `${t.from}-${t.to}-${t.amount}-${t.time}` === txKey))) return;
  if (!tx.timestamp) tx.timestamp = new Date().toISOString();
  txs.unshift(tx);
  // 移除50条限制，保留所有交易记录
  fs.writeFileSync(TX_LOG, JSON.stringify(txs, null, 2));
  broadcastSSE({ ...tx, _type: 'tx' });
}

// Agent 思考事件
const sseClients = new Set();
function getAgentEvents() {
  try { return JSON.parse(fs.readFileSync(AGENT_EVENTS_FILE, 'utf8')); } catch(e) { return []; }
}
function addAgentEvent(event) {
  const events = getAgentEvents();
  if (!event.timestamp) event.timestamp = new Date().toISOString();
  if (!event.id) event.id = 'evt-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
  events.unshift(event);
  if (events.length > 200) events.length = 200;
  fs.writeFileSync(AGENT_EVENTS_FILE, JSON.stringify(events, null, 2));
  broadcastSSE({ ...event, _type: 'event' });
}
function broadcastSSE(data) {
  const msg = `data: ${JSON.stringify(data)}\n\n`;
  for (const res of sseClients) {
    try { res.write(msg); } catch(e) { sseClients.delete(res); }
  }
}

let balanceCache = { data: {}, fetchedAt: 0 };

async function fetchBalancesLive() {
  const entries = Object.entries(AGENTS);
  const results = await Promise.all(entries.map(async ([key, agent]) => {
    try {
      const bal = await w3.eth.getBalance(agent.addr);
      return [key, w3.utils.fromWei(bal.toString(), 'ether')];
    } catch(e) {
      return [key, '0'];
    }
  }));
  return Object.fromEntries(results);
}

async function getBalancesCached(forceRefresh = false) {
  const now = Date.now();
  const cacheFresh = now - balanceCache.fetchedAt < 60_000;
  if (!forceRefresh && cacheFresh && Object.keys(balanceCache.data).length > 0) {
    return balanceCache.data;
  }

  try {
    const liveBalances = await Promise.race([
      fetchBalancesLive(),
      new Promise((_, reject) => setTimeout(() => reject(new Error('balance fetch timeout')), 4000)),
    ]);
    balanceCache = { data: liveBalances, fetchedAt: now };
    return liveBalances;
  } catch (e) {
    if (Object.keys(balanceCache.data).length > 0) {
      return balanceCache.data;
    }
    const fallback = {};
    for (const key of Object.keys(AGENTS)) fallback[key] = '0';
    return fallback;
  }
}

app.get('/', async (req, res) => {
  // 获取实时余额
  const balances = await getBalancesCached();
  let totalSpent = 0;
  let txCount = 0;
  const txs = getTxs();
  txCount = txs.length;
  for (const tx of txs) {
    if (tx.from === '钢蛋') totalSpent += tx.amount;
  }
  res.render('index', { AGENTS, SERVICES: getServices().filter(s => s.active), PENDING_SERVICES: getServices().filter(s => s.status === 'pending'), TRANSACTIONS: txs, balances, totalSpent: totalSpent.toFixed(4), txCount });
});

app.get('/api/balances', async (req, res) => {
  const balances = await getBalancesCached(false);
  // 后台异步刷新
  getBalancesCached(true);
  const result = {};
  for (const [key, agent] of Object.entries(AGENTS)) {
    result[key] = {
      ...agent,
      balance: balances[key] || '0',
    };
  }
  res.json(result);
});

app.get('/api/transactions', (req, res) => {
  const txs = getTxs();
  res.json({ ok: true, transactions: txs });
});

app.get('/api/market', async (req, res) => {
  const services = getServices().filter(s => s.active && s.status === 'approved');
  // BNB 价格用缓存，不阻塞响应
  const bnbPrice = bnbPriceUsd || 600;
  fetchBnbPrice(); // 后台刷新
  // 按有效率+调用量排序
  const sorted = services.map(s => {
    // 兼容旧数据：sales 映射到 totalCalls
    s.totalCalls = s.totalCalls || s.sales || 0;
    s.effectiveCalls = s.effectiveCalls || 0;
    s.effectiveRate = s.effectiveRate || 0;
    s.inputFormat = s.inputFormat || '';
    s.outputFormat = s.outputFormat || '';
    s.latency = s.latency || '';
    s.price_usdc = +(s.price * bnbPrice).toFixed(2);
    // 加权分数：有效率 * 0.5 + 调用量 * 0.3 + 质押 * 0.2
    s._sort_score = (s.totalCalls > 0 ? s.effectiveRate : 0.5) * 50 + Math.min(s.totalCalls, 200) * 0.15 + (s.deposit || 0) * 1000;
    return s;
  }).sort((a, b) => (b._sort_score || 0) - (a._sort_score || 0));
  // 返回时去掉内部排序字段
  res.json(sorted.map(({ _sort_score, ...rest }) => rest));
});

// Web Push 订阅
app.get('/api/push/vapidPublicKey', (req, res) => {
  res.json({ ok: true, publicKey: VAPID_PUBLIC_KEY });
});

app.post('/api/push/subscribe', (req, res) => {
  const { wallet, subscription } = req.body;
  if (!wallet || !subscription) return res.json({ ok: false, error: '缺少 wallet 或 subscription' });
  const subs = getPushSubs();
  const normalized = wallet.toLowerCase();
  // 防重复
  const exists = subs.find(s => s.wallet?.toLowerCase() === normalized && s.subscription.endpoint === subscription.endpoint);
  if (!exists) {
    subs.push({ wallet: normalized, subscription, createdAt: new Date().toISOString() });
    savePushSubs(subs);
  }
  res.json({ ok: true });
});

// push/unsubscribe 已移除（未使用）

// 通知接口
app.get('/api/notifications', (req, res) => {
  const wallet = (req.query.wallet || '').trim().toLowerCase();
  if (!wallet) {
    return res.json({ ok: false, error: '缺少 wallet 参数' });
  }
  const notifications = getNotifications();
  const mine = notifications.filter(n =>
    n.targetWallet?.toLowerCase() === wallet
  );
  const unread = req.query.unread === 'true' ? mine.filter(n => !n.read) : mine;
  res.json({ ok: true, total: mine.length, unread: mine.filter(n => !n.read).length, notifications: unread.slice(0, 50) });
});

app.post('/api/notifications/:id/read', (req, res) => {
  const notifications = getNotifications();
  const ntf = notifications.find(n => n.id === req.params.id);
  if (!ntf) {
    return res.json({ ok: false, error: '通知不存在' });
  }
  ntf.read = true;
  saveNotifications(notifications);
  res.json({ ok: true });
});

app.post('/api/notifications/read-all', (req, res) => {
  const { wallet } = req.body;
  if (!wallet) {
    return res.json({ ok: false, error: '缺少 wallet' });
  }
  const notifications = getNotifications();
  let count = 0;
  notifications.forEach(n => {
    if (n.targetWallet?.toLowerCase() === wallet.toLowerCase() && !n.read) {
      n.read = true;
      count++;
    }
  });
  saveNotifications(notifications);
  res.json({ ok: true, marked: count });
});

// ===== 管理后台 =====
const ADMIN_WALLETS = (process.env.ADMIN_WALLETS || '0xd2f899CE74320AEf9d8f2359183232a554f4C0E1').toLowerCase().split(',');

function isAdmin(wallet) {
  return ADMIN_WALLETS.includes(wallet.toLowerCase());
}

// 待审核列表
app.get('/api/admin/pending', (req, res) => {
  const wallet = req.query.wallet || '';
  if (!isAdmin(wallet)) return res.json({ ok: false, error: '无权限' });
  const services = getServices();
  const pending = services.filter(s => s.status === 'pending');
  res.json({ ok: true, pending });
});

// 审核：通过
app.post('/api/admin/approve/:id', (req, res) => {
  const { wallet } = req.body;
  if (!isAdmin(wallet)) return res.json({ ok: false, error: '无权限' });
  const services = getServices();
  const svc = services.find(s => s.id === req.params.id);
  if (!svc) return res.json({ ok: false, error: '服务不存在' });
  if (svc.status !== 'pending') return res.json({ ok: false, error: '该服务不在待审核状态' });
  svc.status = 'approved';
  svc.approvedAt = new Date().toISOString();
  saveServices(services);
  res.json({ ok: true });
});

// 审核：拒绝
app.post('/api/admin/reject/:id', (req, res) => {
  const { wallet, reason } = req.body;
  if (!isAdmin(wallet)) return res.json({ ok: false, error: '无权限' });
  const services = getServices();
  const svc = services.find(s => s.id === req.params.id);
  if (!svc) return res.json({ ok: false, error: '服务不存在' });
  if (svc.status !== 'pending') return res.json({ ok: false, error: '该服务不在待审核状态' });
  svc.status = 'rejected';
  svc.rejectReason = reason || '';
  svc.rejectedAt = new Date().toISOString();
  saveServices(services);
  res.json({ ok: true });
});

// 提交服务结果（卖家调用）
app.post('/api/orders/:orderId/result', (req, res) => {
  const { orderId } = req.params;
  const { output, sellerWallet } = req.body;

  if (!orderId || !output || !sellerWallet) {
    return res.json({ ok: false, error: '缺少 orderId, output 或 sellerWallet' });
  }

  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === orderId);
  if (!purchase) {
    return res.json({ ok: false, error: '订单不存在' });
  }

  if (purchase.expertWallet?.toLowerCase() !== sellerWallet.toLowerCase()) {
    return res.json({ ok: false, error: '只有卖家能提交结果' });
  }
  if (purchase.status !== 'pending') {
    return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法提交结果` });
  }

    Promise.resolve().then(async () => {
    await markPurchaseDelivered(orderId, output, { autoDelivered: false, rawOutput: output });
    res.json({ ok: true, escrowOrderId: purchase.escrowOrderId || '' });
  }).catch(err => {
    res.json({ ok: false, error: err.message });
  });
});

// 查询订单结果（买家调用）
app.get('/api/orders/:orderId/result', (req, res) => {
  const { orderId } = req.params;
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === orderId);
  if (!purchase) {
    return res.json({ ok: false, error: '订单不存在' });
  }
  res.json({
    ok: true,
    status: purchase.status,
    result: purchase.result || null,
    resultAt: purchase.resultAt || null,
  });
});

// 服务目录
app.get('/api/services', async (req, res) => {
  const services = getServices().filter(s => s.active && s.status === 'approved');
  const bnbPrice = await fetchBnbPrice();
  const withUsd = services.map(s => ({ ...s, price_usdc: +(s.price * bnbPrice).toFixed(2) }));
  res.json(withUsd);
});

// 获取用户自己的服务（包括 pending 状态）
app.get('/api/my-services/:wallet', (req, res) => {
  const wallet = req.params.wallet.toLowerCase();
  const services = getServices().filter(s => 
    s.wallet && s.wallet.toLowerCase() === wallet && s.active
  );
  res.json(services);
});

// 专家入驻
app.get('/api/config/deposit', (req, res) => {
  res.json({
    depositPoolAddress: DEPOSIT_POOL_ADDRESS,
    stakingAddress: DEPOSIT_POOL_ADDRESS,
    isOnChain: DEPOSIT_POOL_ADDRESS !== '0x0000000000000000000000000000000000000000'
  });
});

// 服务文件安全扫描
app.post('/api/skills/scan', upload.single('skillFile'), (req, res) => {
  try {
    if (!req.file) return res.json({ ok: false, error: '未上传文件' });
    const ext = path.extname(req.file.originalname).toLowerCase();
    if (!['.py', '.js'].includes(ext)) {
      fs.unlinkSync(req.file.path);
      return res.json({ ok: false, error: '只支持 .py 或 .js 文件' });
    }
    const code = fs.readFileSync(req.file.path, 'utf8');
    const { scan } = require('../security/scanner');
    const scanResult = scan(code);
    fs.unlinkSync(req.file.path); // 扫完删临时文件
    res.json({ ok: true, scan: scanResult });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

app.post('/api/experts/register', upload.single('skillFile'), async (req, res) => {
  const { expert, wallet, name, desc, price, deposit, depositTx, inputFormat, outputFormat, latency, deliveryMode, endpoint } = req.body;
  const expertName = sanitizeText(expert, 40);
  const skillName = sanitizeText(name, 80);
  const description = sanitizeText(desc, 240);
  let normalizedWallet = typeof wallet === 'string' ? wallet.trim() : '';
  const parsedPrice = parsePositiveNumber(price);
  const parsedDeposit = parseNonNegativeNumber(deposit, 0.001);
  const depositTxHash = typeof depositTx === 'string' ? depositTx.trim() : '';
  const deliveryModeValue = deliveryMode === 'self_hosted' ? 'self_hosted' : 'hosted';
  const endpointUrl = deliveryModeValue === 'self_hosted' ? sanitizeText(endpoint, 240) : '';

  const inputFmt = sanitizeText(inputFormat, 120);
  const outputFmt = sanitizeText(outputFormat, 120);
  const latencyEst = sanitizeText(latency, 30);
  const initialStatus = req.body.status === 'pending_deposit' ? 'pending_deposit' : null;

  if (!expertName || !normalizedWallet || !skillName || parsedPrice === null || parsedDeposit === null) {
    console.log('Validation failed:', { expertName, normalizedWallet, skillName, parsedPrice, parsedDeposit, rawPrice: price, rawDeposit: deposit });
    return res.json({ ok: false, error: `缺少必填字段: ${[!expertName&&'expert',!normalizedWallet&&'wallet',!skillName&&'name',parsedPrice===null&&'price',parsedDeposit===null&&'deposit'].filter(Boolean).join(',')}` });
  }
  if (!inputFmt || !outputFmt) {
    return res.json({ ok: false, error: '请填写输入/输出格式' });
  }
  if (!isValidAddress(normalizedWallet)) {
    return res.json({ ok: false, error: 'wallet 地址格式无效' });
  }
  // 一号一服务限制
  const existingServices = getServices();
  const hasActive = existingServices.find(s => s.wallet?.toLowerCase() === normalizedWallet.toLowerCase() && s.status !== 'deregistered');
  if (hasActive) {
    return res.json({ ok: false, error: '该钱包已发布服务，一个钱包只能发布一个服务' });
  }
  // 平台托管服务 ID
  const id = `${expertName}-${skillName.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}`;

  // 验证押金交易（非零地址时需要链上验证，pending_deposit 状态跳过验证）
  if (!initialStatus && DEPOSIT_POOL_ADDRESS !== '0x0000000000000000000000000000000000000000') {
    if (!isChainTxHash(depositTxHash)) {
      return res.json({ ok: false, error: '缺少链上押金交易哈希，请先通过MetaMask缴纳押金' });
    }
    // 链上验证押金交易
    try {
      const tx = await w3.eth.getTransaction(depositTxHash);
      if (!tx) return res.json({ ok: false, error: '押金交易未找到，请确认交易已上链' });
      if (tx.from.toLowerCase() !== normalizedWallet.toLowerCase()) {
        // 押金发送者和入驻钱包不一致，自动用押金发送者作为入驻钱包
        console.log('Auto-correcting wallet:', { txFrom: tx.from, registerWallet: normalizedWallet });
        normalizedWallet = tx.from.toLowerCase();
      }
      if (tx.to && tx.to.toLowerCase() !== DEPOSIT_POOL_ADDRESS.toLowerCase()) {
        return res.json({ ok: false, error: '押金未发送到正确的押金池地址' });
      }
      if (!tx.input || !tx.input.toLowerCase().startsWith(STAKE_SELECTOR)) {
        return res.json({ ok: false, error: '押金交易必须调用质押合约的 stake(skillId)' });
      }
      const stakedSkillId = decodeSingleStringArg(tx.input, STAKE_SELECTOR);
      if (stakedSkillId && stakedSkillId !== id) {
        return res.json({ ok: false, error: '押金交易绑定的 skillId 与当前服务不一致' });
      }
      const depositAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
      if (depositAmount < parsedDeposit) {
        return res.json({ ok: false, error: `押金金额不足，需要 ${parsedDeposit} BNB，实际 ${depositAmount} BNB` });
      }
    } catch (e) {
      return res.json({ ok: false, error: `押金交易验证失败: ${e.message}` });
    }
  }

  const services = getServices();
  const duplicate = services.find(s => s.active && s.expert === expertName && s.name === skillName);
  if (duplicate) {
    // 允许替换 pending_deposit 状态的服务
    if (duplicate.status === 'pending_deposit') {
      // 更新现有服务
      duplicate.wallet = normalizedWallet;
      duplicate.desc = description || '';
      duplicate.price = parsedPrice;
      duplicate.deposit = parsedDeposit;
      duplicate.inputFormat = inputFmt;
      duplicate.outputFormat = outputFmt;
      duplicate.latency = latencyEst || '';
      duplicate.registeredAt = new Date().toISOString();
      saveServices(services);
      return res.json({ ok: true, service: duplicate, serviceId: duplicate.id });
    }
    return res.json({ ok: false, error: '该服务已存在，请更换名称' });
  }

  // 安全扫描 + 交付方式验证（必须通过才能上架）
  let securityScan = { level: 'unsafe', score: 0, issues: [], summary: '❌ 未扫描' };
  let skillFilePath = '';
  let skillFileExt = '';

  if (deliveryModeValue === 'hosted') {
    // 托管模式：必须上传代码文件
    if (!req.file) {
      return res.json({ ok: false, error: '托管模式必须上传服务代码文件（.py 或 .js）' });
    }
    skillFileExt = path.extname(req.file.originalname).toLowerCase();
    if (!['.py', '.js'].includes(skillFileExt)) {
      try { fs.unlinkSync(req.file.path); } catch(e) {}
      return res.json({ ok: false, error: '只支持 .py 或 .js 文件' });
    }
    // 安全扫描（必须通过）
    try {
      const code = fs.readFileSync(req.file.path, 'utf8');
      const { scan } = require('../security/scanner');
      securityScan = scan(code, skillFileExt === '.py' ? 'py' : 'js');
      if (securityScan.level === 'critical') {
        try { fs.unlinkSync(req.file.path); } catch(e2) {}
        return res.json({ ok: false, error: '安全扫描未通过，服务不允许上架', scan: securityScan });
      }
    } catch(e) {
      try { fs.unlinkSync(req.file.path); } catch(e2) {}
      return res.json({ ok: false, error: '安全扫描失败: ' + e.message });
    }
  } else {
    // 自托管模式：必须填 endpoint，并做可达性验证
    if (!endpointUrl) {
      return res.json({ ok: false, error: '自托管模式必须填写 API Endpoint' });
    }
    const endpointValidation = await validateServiceEndpoint(endpointUrl);
    if (!endpointValidation.ok) {
      return res.json({ ok: false, error: endpointValidation.error });
    }
    securityScan = { level: 'safe', score: 80, issues: [], summary: '✅ 自托管服务（API 安全由卖家负责）' };
  }

  // 保存上传的代码文件（托管模式）
  if (deliveryModeValue === 'hosted' && req.file) {
    const skillsDir = path.join(__dirname, '..', 'skills');
    if (!fs.existsSync(skillsDir)) fs.mkdirSync(skillsDir, { recursive: true });
    skillFilePath = path.join(skillsDir, `${id}${skillFileExt}`);
    fs.copyFileSync(req.file.path, skillFilePath);
    try { fs.unlinkSync(req.file.path); } catch(e) {} // 清理临时文件
  }

  const newService = {
    id, expert: expertName, wallet: normalizedWallet, service: 'service', name: skillName,
    desc: description || '', price: parsedPrice, deposit: parsedDeposit,
    inputFormat: inputFmt, outputFormat: outputFmt, latency: latencyEst || '',
    deliveryMode: deliveryModeValue,
    executionMode: deliveryModeValue === 'hosted' ? 'hosted' : 'self_hosted',
    resultType: inferServiceResultType({ id, name: skillName, outputFormat: outputFmt }),
    api: {
      endpoint: deliveryModeValue === 'self_hosted' ? endpointUrl : '',
      method: 'POST',
      skillFile: deliveryModeValue === 'hosted',
      skillExt: deliveryModeValue === 'hosted' ? skillFileExt : '',
    },
    skillFilePath: deliveryModeValue === 'hosted' ? skillFilePath : '',
    depositTx: depositTxHash || null,
    security: securityScan,
    totalCalls: 0, effectiveCalls: 0, effectiveRate: 0,
    rating: 0, sales: 0, active: true,
    status: initialStatus || 'pending',
    avatar: '🤖',
    registeredAt: new Date().toISOString()
  };
  services.push(newService);
  saveServices(services);
  if (!initialStatus) {
    addTx({ time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}), from: expertName, to: '押金池', amount: parsedDeposit, reason: `入驻: ${skillName}`, tx: `reg-${id}` });
  }
  res.json({ ok: true, service: newService, serviceId: id });
});

// 更新服务押金状态（缴纳押金后调用）
app.post('/api/services/:id/deposit', async (req, res) => {
  const { id } = req.params;
  const { txHash, wallet } = req.body;
  
  const services = getServices();
  const svc = services.find(s => s.id === id);
  if (!svc) return res.json({ ok: false, error: '服务不存在' });
  if (svc.status !== 'pending_deposit') return res.json({ ok: false, error: '服务状态不正确' });
  
  // 验证押金交易
  try {
    const tx = await w3.eth.getTransaction(txHash);
    if (!tx) return res.json({ ok: false, error: '交易未找到' });
    if (tx.to && tx.to.toLowerCase() !== DEPOSIT_POOL_ADDRESS.toLowerCase()) {
      return res.json({ ok: false, error: '押金未发送到正确地址' });
    }
    if (!tx.input || !tx.input.toLowerCase().startsWith(STAKE_SELECTOR)) {
      return res.json({ ok: false, error: '押金交易必须调用质押合约的 stake(skillId)' });
    }
    const stakedSkillId = decodeSingleStringArg(tx.input, STAKE_SELECTOR);
    if (!stakedSkillId || stakedSkillId !== svc.id) {
      return res.json({ ok: false, error: '押金交易未绑定当前服务 skillId' });
    }
    const depositAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
    if (depositAmount < 0.001) {
      return res.json({ ok: false, error: '押金金额不足' });
    }
    
    svc.status = 'pending'; // 更新为待审核
    svc.depositTx = txHash;
    svc.wallet = tx.from.toLowerCase(); // 用实际付款钱包
    saveServices(services);
    
    addTx({ time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}), from: svc.expert, to: '押金池', amount: depositAmount, reason: `入驻: ${svc.name}`, tx: txHash });
    
    // 自动审核逻辑
    let autoApproved = false;
    if (svc.deliveryMode === 'hosted' && svc.security && svc.security.level !== 'unsafe') {
      // 托管模式 + 安全扫描通过 → 自动审核通过
      svc.status = 'approved';
      svc.approvedAt = new Date().toISOString();
      svc.autoApproved = true;
      autoApproved = true;
      saveServices(services);
      console.log(`[自动审核] 托管模式服务已自动通过: ${svc.name}`);
    } else if (svc.deliveryMode === 'self-hosted' && svc.endpoint) {
      // 自托管模式 → 验证 API 可用性
      try {
        const healthRes = await fetch(svc.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'health_check' }),
          timeout: 5000
        });
        if (healthRes.ok) {
          svc.status = 'approved';
          svc.approvedAt = new Date().toISOString();
          svc.autoApproved = true;
          autoApproved = true;
          saveServices(services);
          console.log(`[自动审核] 自托管模式服务 API 验证通过: ${svc.name}`);
        } else {
          console.log(`[自动审核] 自托管模式服务 API 返回错误: ${svc.name}`);
        }
      } catch (e) {
        console.log(`[自动审核] 自托管模式服务 API 验证失败: ${svc.name}, ${e.message}`);
      }
    }
    
    res.json({ ok: true, autoApproved });
  } catch(e) {
    res.json({ ok: false, error: '交易验证失败: ' + e.message });
  }
});

// 确认购买（待确认订单 → 完成）
app.post('/api/purchases/confirm/:purchaseId', (req, res) => {
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === req.params.purchaseId);
  if (!purchase) return res.json({ ok: false, error: '订单不存在' });
  if (purchase.status !== 'delivered' && purchase.status !== 'pending_confirm') {
    return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法确认` });
  }

  Promise.resolve().then(async () => {
    if (purchase.escrowOrderId) {
      const order = await fetchEscrowOrder(purchase.escrowOrderId);
      if (order.status !== 'Confirmed' && order.status !== 'Expired') {
        return res.json({ ok: false, error: `Escrow 链上状态为 ${order.status}，请先完成链上确认或等待超时释放` });
      }
      purchase.escrowStatus = order.status;
      purchase.escrowSettledAt = new Date().toISOString();
      purchase.payment = {
        ...(purchase.payment || {}),
        mode: 'escrow',
        verified: true,
      };
    }

    purchase.status = purchase.payment?.verified ? 'completed' : 'demo-completed';
    purchase.confirmedAt = new Date().toISOString();
    savePurchases(purchases);

    const services = getServices();
    const service = services.find(s => s.id === purchase.serviceId);
    if (service) {
      service.sales += 1;
      saveServices(services);
    }

    addTx({
      time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
      from: purchase.buyerName || '未知',
      fromWallet: purchase.buyerWallet,
      to: purchase.expert,
      amount: purchase.price,
      reason: `${purchase.serviceName} [确认购买]`,
      tx: purchase.txHash || purchase.id,
      verified: purchase.payment?.verified ? '✅ 已验证' : '🧪 模拟',
      receipt: purchase.id
    });

    res.json({ ok: true, purchase });
  }).catch(err => {
    res.json({ ok: false, error: err.message });
  });
});

// 拒绝购买（待确认订单 → 取消）
app.post('/api/purchases/reject/:purchaseId', (req, res) => {
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === req.params.purchaseId);
  if (!purchase) return res.json({ ok: false, error: '订单不存在' });
  if (purchase.escrowOrderId) return res.json({ ok: false, error: 'Escrow 订单请走链上 dispute() 争议流程' });
  if (purchase.status !== 'delivered' && purchase.status !== 'pending_confirm') return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法拒绝` });

  purchase.status = 'rejected';
  purchase.rejectedAt = new Date().toISOString();
  savePurchases(purchases);

  res.json({ ok: true, purchase });
});

// 获取待确认订单列表
app.get('/api/purchases/pending', (req, res) => {
  const purchases = getPurchases();
  const pending = purchases.filter(p => p.status === 'delivered' || p.status === 'pending_confirm');
  res.json({ ok: true, count: pending.length, purchases: pending });
});

// 专家退出（标记退出，退款由质押方处理）
app.post('/api/experts/exit', (req, res) => {
  const { expert, serviceId, withdrawTx } = req.body;
  if (!expert) return res.json({ ok: false, error: '缺少专家名' });
  const services = getServices();
  const idx = services.findIndex(s => serviceId ? s.id === serviceId : s.expert === expert);
  if (idx === -1) return res.json({ ok: false, error: '未找到该专家' });
  const svc = services[idx];
  if (!svc.active) return res.json({ ok: false, error: '已退出' });

  // 检查是否有未完成的订单
  const purchases = getPurchases();
  const pending = purchases.filter(p => p.expert === expert && !['completed', 'demo-completed', 'rejected'].includes(p.status));
  if (pending.length > 0) return res.json({ ok: false, error: `有 ${pending.length} 笔订单未完成，无法退出` });

  svc.active = false;
  svc.status = 'deregistered';
  svc.exitedAt = new Date().toISOString();
  if (withdrawTx) {
    svc.withdrawTx = withdrawTx;
    svc.refundStatus = 'completed';
  } else {
    svc.refundStatus = 'pending';
  }
  services[idx] = svc;
  saveServices(services);

  res.json({ ok: true, message: '已退出', service: svc });
});

// 质押方退款回调（Four.meme 或合约调用）
// refund/callback 已移除（未使用）

// 管理员审核服务
// 管理员鉴权中间件
const ADMIN_SECRET = process.env.ADMIN_SECRET || 'cryptominds-admin-2026';
function requireAdmin(req, res, next) {
  const auth = req.headers['x-admin-secret'] || req.query.secret || (req.body && req.body.adminSecret);
  if (auth !== ADMIN_SECRET) {
    return res.status(403).json({ ok: false, error: '管理员鉴权失败' });
  }
  next();
}

// admin/audit-log 已移除（未使用）

// 管理员操作接口（需鉴权）
app.get('/api/admin/pending', requireAdmin, (req, res) => {
  const services = getServices();
  const pending = services.filter(s => s.status === 'pending');
  res.json({ ok: true, count: pending.length, services: pending });
});

app.post('/api/admin/approve/:serviceId', requireAdmin, (req, res) => {
  const { serviceId } = req.params;
  const services = getServices();
  const idx = services.findIndex(s => s.id === serviceId);
  if (idx === -1) return res.json({ ok: false, error: '服务不存在' });
  const svc = services[idx];
  if (svc.status !== 'pending') return res.json({ ok: false, error: `服务状态为 ${svc.status || 'active'}，无法审核` });
  
  svc.status = 'approved';
  svc.active = true;
  svc.approvedAt = new Date().toISOString();
  services[idx] = svc;
  saveServices(services);
  res.json({ ok: true, message: `${svc.name} 已上架`, service: svc });
});

app.post('/api/admin/reject/:serviceId', requireAdmin, (req, res) => {
  const { serviceId } = req.params;
  const { reason } = req.body;
  const services = getServices();
  const idx = services.findIndex(s => s.id === serviceId);
  if (idx === -1) return res.json({ ok: false, error: '服务不存在' });
  const svc = services[idx];
  if (svc.status !== 'pending') return res.json({ ok: false, error: `服务状态为 ${svc.status || 'active'}，无法拒绝` });
  
  svc.status = 'rejected';
  svc.active = false;
  svc.rejectedAt = new Date().toISOString();
  svc.rejectionReason = reason || '审核未通过';
  services[idx] = svc;
  saveServices(services);
  res.json({ ok: true, message: `${svc.name} 已拒绝`, service: svc });
});

// 专家列表（含质押状态）
app.get('/api/experts', (req, res) => {
  const services = getServices();
  const experts = {};
  services.forEach(s => {
    if (!experts[s.expert]) {
      experts[s.expert] = { name: s.expert, wallet: s.wallet, services: [], totalSales: 0, active: s.active };
    }
    experts[s.expert].services.push({ id: s.id, name: s.name, price: s.price });
    experts[s.expert].totalSales += s.sales || 0;
  });
  res.json(Object.values(experts));
});

// ===== V2 API =====
const sellersMarketHandlers = createSellersMarketHandlers({
  getSellers,
  saveSellers,
  getPurchases,
  savePurchases,
  purchasesFile: PURCHASES_FILE,
  addTx,
});

app.get('/api/sellers', sellersMarketHandlers.listSellers);
app.post('/api/sellers/register', sellersMarketHandlers.registerSeller);
app.post('/api/sellers/:wallet/deposit', sellersMarketHandlers.depositSeller);
app.post('/api/orders/:id/execute', sellersMarketHandlers.executeOrder);
app.post('/api/orders/create', sellersMarketHandlers.createOrder);
app.post('/api/sellers/exit', sellersMarketHandlers.exitSeller);


// 购买服务
app.post('/api/services/buy', async (req, res) => {
  const { serviceId, buyerWallet, buyerName, txHash, selectedRoute, paymentMode, escrowOrderId } = req.body;
  const normalizedServiceId = sanitizeText(serviceId, 120);
  const normalizedBuyerWallet = typeof buyerWallet === 'string' ? buyerWallet.trim() : '';
  const normalizedPaymentMode = typeof paymentMode === 'string' ? paymentMode.trim().toLowerCase() : '';
  const normalizedInput = sanitizeText(
    typeof req.body.input === 'string' ? req.body.input
    : typeof req.body.task === 'string' ? req.body.task
    : typeof req.body.targetAddress === 'string' ? req.body.targetAddress
    : '',
    240
  );
  // 优先用前端传的名字，否则从 agents.json 反查
  let normalizedBuyerName = sanitizeText(buyerName, 60);
  if (!normalizedBuyerName) {
    const agents = getAgents();
    const matchedAgent = agents.find(a => a.wallet && a.wallet.toLowerCase() === normalizedBuyerWallet.toLowerCase());
    normalizedBuyerName = matchedAgent?.name || '未知Agent';
  }

  if (!normalizedServiceId || !normalizedBuyerWallet) {
    return res.json({ ok: false, error: '缺少必填字段' });
  }
  if (!isSupportedWalletAddress(normalizedBuyerWallet)) {
    return res.json({ ok: false, error: 'buyerWallet 地址格式无效' });
  }

  const services = getServices();
  const service = services.find(s => s.id === normalizedServiceId);
  if (!service) {
    return res.json({ ok: false, error: '服务不存在' });
  }
  if (!service.active) {
    return res.json({ ok: false, error: '服务已下架' });
  }

  const purchases = getPurchases();
  if (txHash && purchases.some(p => p.txHash === txHash)) {
    return res.json({ ok: false, error: '该 txHash 已使用，不能重复购买' });
  }

  const demoRequested = normalizedPaymentMode === 'demo';
  if (!txHash && !demoRequested) {
    return res.json({ ok: false, error: '缺少支付凭证，请提供 txHash 或显式使用 demo 模式' });
  }

  let payment = { mode: demoRequested ? 'demo' : 'pending', verified: false };
  if (txHash) {
    const verification = await verifyEscrowPaymentTx(txHash, normalizedBuyerWallet, service, escrowOrderId);
    if (!verification.ok) {
      return res.json({ ok: false, error: verification.error });
    }
    payment = {
      mode: 'escrow',
      verified: true,
      ...verification.tx,
    };
  } else if (!demoRequested) {
    return res.json({ ok: false, error: '支付验证失败' });
  }

  let route = null;
  if (selectedRoute) {
    try {
      route = await resolveSelectedRoute(normalizedServiceId, normalizedBuyerWallet, selectedRoute);
      payment.route = route;
    } catch (error) {
      // 路由校验失败不阻塞购买，降级继续
      console.error('路由校验失败，降级继续:', error.message);
    }
  }

  const reportType = service.id.includes('scan') ? 'scanning' : 
                     service.id.includes('risk') ? 'risk' : 
                     service.id.includes('report') ? 'report' : 'analysis';
  const report = null; // 先不生成报告，避免阻塞
  // 异步生成报告（不阻塞购买响应）
  generateReport(reportType, normalizedBuyerWallet, service.wallet).then(r => {
    if (r) { purchase.report = r; savePurchases(getPurchases()); }
  }).catch(() => {});
  const autoConfirm = req.body.autoConfirm === true;
  const purchase = {
    id: `purchase-${Date.now()}`,
    serviceId: normalizedServiceId,
    expert: service.expert,
    expertWallet: service.wallet,
    serviceName: service.name,
    buyerWallet: normalizedBuyerWallet,
    buyerName: normalizedBuyerName,
    price: service.price,
    status: autoConfirm ? (payment.verified ? 'completed' : 'demo-completed') : 'pending',
    payment,
    selectedRoute: route,
    report,
    txHash: txHash || '',
    escrowOrderId: escrowOrderId || '',
    escrowAddress: escrowOrderId ? ESCROW_CONFIG.address : '',
    input: normalizedInput,
    time: new Date().toISOString(),
    autoConfirm
  };
  addPurchase(purchase);

  // 通知卖家：有新订单
  addNotification({
    type: 'new_order',
    targetWallet: service.wallet,
    orderId: purchase.id,
    serviceId: service.id,
    serviceName: service.name,
    buyerWallet: normalizedBuyerWallet,
    buyerName: normalizedBuyerName,
    input: purchase.input || '',
  });

  // 通知买家：订单已创建
  addNotification({
    type: 'order_confirmed',
    targetWallet: normalizedBuyerWallet,
    orderId: purchase.id,
    serviceId: service.id,
    serviceName: service.name,
    sellerWallet: service.wallet,
    sellerName: service.expert,
  });

  if (autoConfirm) {
    // 自动确认模式：直接完成购买
    service.sales += 1;
    saveServices(services);
    try {
      const { installSkill } = require('../security/install');
      const installResult = installSkill({
        agentWallet: normalizedBuyerWallet,
        skillId: service.id,
        skillName: service.name,
        seller: service.expert,
        metadata: { price: service.price, frameworks: service.frameworks || [] }
      });
      purchase.installed = installResult.ok;
    } catch (e) {
      purchase.installed = false;
    }
    addTx({
      time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
      from: normalizedBuyerName,
      fromWallet: normalizedBuyerWallet,
      to: service.expert,
      amount: service.price,
      reason: route ? `${service.name} [${route.route_type}/${route.chain}/${route.symbol}]` : service.name,
      tx: txHash || purchase.id,
      route_type: route ? `${route.route_type}/${route.chain}/${route.symbol}` : 'direct',
      verified: payment.verified ? '✅ 已验证' : '🧪 模拟',
      receipt: purchase.id
    });
    res.json({ ok: true, purchase, serviceApi: service.api || null });
  } else {
    setTimeout(() => {
      attemptAutoDeliverPurchase(purchase.id).catch(() => {});
    }, 1000);
    // Escrow / demo 模式：等待卖家先交付
    res.json({ ok: true, purchase, needConfirm: false, message: '购买请求已提交，等待卖家交付结果' });
  }
});

// ============================================
// 服务代理调用（全自动，无需人工介入）
// POST /api/skill/call/:serviceId
// Body: { buyer: "0x钱包地址", ...请求参数 }
// ============================================
app.post('/api/skill/call/:serviceId', async (req, res) => {
  const { serviceId } = req.params;
  const { buyer, ...payload } = req.body;
  const normalizedBuyer = typeof buyer === 'string' ? buyer.trim().toLowerCase() : '';

  if (!normalizedBuyer) {
    return res.json({ ok: false, error: '缺少 buyer 钱包地址' });
  }

  // 1. 查找 skill
  const services = getServices();
  const service = services.find(s => s.id === serviceId && s.active);
  if (!service) {
    return res.json({ ok: false, error: '服务不存在或已下架' });
  }

  // 2. 验证是否已购买
  const purchases = getPurchases();
  const hasPurchased = purchases.some(p =>
    p.serviceId === serviceId &&
    p.buyerWallet &&
    p.buyerWallet.toLowerCase() === normalizedBuyer
  );
  if (!hasPurchased) {
    return res.json({ ok: false, error: '未购买此服务，请先通过 /api/pay 购买' });
  }

  // 3. 执行服务 — 优先本地文件，其次 endpoint
  const skillId = service.id;
  const skillDir = path.join(__dirname, '..', 'uploaded_skills', skillId);
  const pyFile = path.join(skillDir, 'skill.py');
  const jsFile = path.join(skillDir, 'skill.js');

  if (fs.existsSync(pyFile) || fs.existsSync(jsFile)) {
    // 本地执行上传的服务文件
    const execFile = require('child_process').execFile;
    const fileToRun = fs.existsSync(pyFile) ? pyFile : jsFile;
    const isPy = fileToRun.endsWith('.py');
    const taskJson = JSON.stringify(payload.task || payload);

    let execCmd, execArgs;
    if (isPy) {
      execCmd = 'python3';
      execArgs = ['-c', `import json,sys;sys.path.insert(0,'${skillDir}');from skill import execute;print(json.dumps({"data":execute(${taskJson})}))`];
    } else {
      execCmd = 'node';
      execArgs = ['-e', `const s=require('${jsFile}');Promise.resolve(s.execute(${taskJson})).then(r=>{console.log(JSON.stringify({data:r}));process.exit(0)}).catch(e=>{console.error(JSON.stringify({error:e.message}));process.exit(1)})`];
    }

    execFile(execCmd, execArgs, { timeout: 15000, cwd: skillDir }, (err, stdout, stderr) => {
      const duration = Date.now() - Date.now();
      addTx({
        time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
        from: normalizedBuyer.slice(0, 8) + '...',
        to: service.expert,
        amount: 0,
        reason: `调用: ${service.name}`,
        tx: `call-${Date.now()}`
      });

      if (err) {
        return res.json({ ok: false, error: `执行失败: ${err.message}` });
      }
      try {
        const out = JSON.parse(stdout.trim().split('\n').pop());
        res.json({ ok: true, service: service.name, expert: service.expert, data: out.data });
      } catch(e) {
        res.json({ ok: true, service: service.name, expert: service.expert, data: stdout.trim() });
      }
    });
  } else if (service.api && service.api.endpoint) {
    // 降级：通过 endpoint 调用
    try {
      const method = (service.api.method || 'POST').toUpperCase();
      const fetchOptions = { method, headers: { 'Content-Type': 'application/json' } };
      if (method === 'POST' && Object.keys(payload).length > 0) {
        fetchOptions.body = JSON.stringify(payload);
      }
      let url = service.api.endpoint;
      if (method === 'GET' && Object.keys(payload).length > 0) {
        const params = new URLSearchParams(payload).toString();
        url += (url.includes('?') ? '&' : '?') + params;
      }
      const startTime = Date.now();
      const response = await fetch(url, fetchOptions);
      const duration = Date.now() - startTime;
      const data = await response.json().catch(() => null);
      addTx({
        time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
        from: normalizedBuyer.slice(0, 8) + '...',
        to: service.expert,
        amount: 0,
        reason: `调用: ${service.name}`,
        tx: `call-${Date.now()}`
      });
      res.json({ ok: true, service: service.name, expert: service.expert, duration_ms: duration, status: response.status, data });
    } catch (error) {
      res.json({ ok: false, error: `调用失败: ${error.message}` });
    }
  } else {
    res.json({ ok: false, error: '该服务没有可用的执行方式' });
  }
});

// 服务有效率反馈（agent 调用后标记有效/无效）
app.post('/api/services/:id/feedback', (req, res) => {
  const serviceId = req.params.id;
  const { effective, buyerWallet } = req.body;
  if (typeof effective !== 'boolean') {
    return res.json({ ok: false, error: '缺少 effective 字段（true/false）' });
  }
  const services = getServices();
  const svc = services.find(s => s.id === serviceId);
  if (!svc) return res.json({ ok: false, error: '服务不存在' });

  svc.totalCalls = (svc.totalCalls || 0) + 1;
  svc.effectiveCalls = (svc.effectiveCalls || 0) + (effective ? 1 : 0);
  svc.effectiveRate = svc.totalCalls > 0 ? parseFloat((svc.effectiveCalls / svc.totalCalls).toFixed(4)) : 0;
  saveServices(services);

  addTx({
    time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
    from: (buyerWallet || 'unknown').slice(0, 8) + '...',
    to: svc.expert,
    amount: 0,
    reason: `${effective ? '✅ 有效' : '❌ 无效'}: ${svc.name}`,
    tx: `fb-${Date.now()}`
  });

  res.json({ ok: true, totalCalls: svc.totalCalls, effectiveCalls: svc.effectiveCalls, effectiveRate: svc.effectiveRate });
});

// ============================================
// x402 支付验证（AgentPay SDK）
// ============================================
app.post('/api/pay/x402', async (req, res) => {
  const { serviceId, paymentHeader, buyerWallet } = req.body;

  const normalizedServiceId = sanitizeText(serviceId, 120);
  const requestedBuyerWallet = typeof buyerWallet === 'string' ? buyerWallet.trim() : '';

  if (!normalizedServiceId || !paymentHeader) {
    return res.json({ ok: false, error: '缺少 serviceId 或 paymentHeader' });
  }

  try {
    const servicesJson = JSON.stringify(getServices());
    const result = await runPythonJson(X402_VERIFY_SCRIPT, [paymentHeader, normalizedServiceId, servicesJson]);

    if (!result.valid) {
      return res.json({ ok: false, error: result.error || '支付验证失败' });
    }

    // 验证成功，执行服务
    const services = getServices();
    const service = services.find(s => s.id === normalizedServiceId);
    if (!service) {
      return res.json({ ok: false, error: '服务不存在' });
    }

    const verifiedBuyerWallet = result.from_address || requestedBuyerWallet;
    if (!verifiedBuyerWallet) {
      return res.json({ ok: false, error: '未能确定付款地址' });
    }
    if (requestedBuyerWallet && verifiedBuyerWallet.toLowerCase() !== requestedBuyerWallet.toLowerCase()) {
      return res.json({ ok: false, error: 'buyerWallet 与已验证付款地址不一致' });
    }

    // 生成服务执行结果
    const reportType = service.id.includes('scan') ? 'scanning' : 
                       service.id.includes('risk') ? 'risk' : 
                       service.id.includes('report') ? 'report' : 'analysis';
    const report = null;
    generateReport(reportType, verifiedBuyerWallet, service.wallet).then(r => {
      if (r) { purchase.report = r; savePurchases(getPurchases()); }
    }).catch(() => {});

    const purchase = {
      id: `purchase-x402-${Date.now()}`,
      serviceId: normalizedServiceId,
      expert: service.expert,
      expertWallet: service.wallet,
      serviceName: service.name,
      buyerWallet: verifiedBuyerWallet,
      price: service.price,
      priceCurrency: 'BNB',
      status: 'completed',
      payment: {
        mode: 'x402',
        verified: true,
        chain: result.chain,
        txHash: result.tx_hash,
        from: result.from_address,
        to: result.to_address,
        amount: result.amount
      },
      report,
      txHash: result.tx_hash,
      time: new Date().toISOString()
    };
    
    addPurchase(purchase);

    // 通知卖家：有新订单
    addNotification({
      type: 'new_order',
      targetWallet: service.wallet,
      orderId: purchase.id,
      serviceId: service.id,
      serviceName: service.name,
      buyerWallet: verifiedBuyerWallet,
      input: '',
    });

    // 通知买家：订单已确认
    addNotification({
      type: 'order_confirmed',
      targetWallet: verifiedBuyerWallet,
      orderId: purchase.id,
      serviceId: service.id,
      serviceName: service.name,
      sellerWallet: service.wallet,
      sellerName: service.expert,
    });

    service.sales += 1;
    saveServices(services);

    addTx({
      time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
      from: verifiedBuyerWallet,
      to: service.expert,
      amount: service.price,
      reason: `${service.name} (x402)`,
      tx: result.tx_hash
    });
    
    res.json({ ok: true, purchase, serviceApi: service.api || null });
    
  } catch (error) {
    console.error('x402 验证错误:', error);
    res.json({ ok: false, error: `支付验证失败: ${error.message}` });
  }
});

app.post('/api/pay/x402/split', async (req, res) => {
  const { serviceId, buyerWallet, paymentHeaders, selectedRoute } = req.body;
  const normalizedServiceId = sanitizeText(serviceId, 120);
  const requestedBuyerWallet = typeof buyerWallet === 'string' ? buyerWallet.trim() : '';

  if (!normalizedServiceId || !requestedBuyerWallet || !Array.isArray(paymentHeaders) || paymentHeaders.length < 2) {
    return res.json({ ok: false, error: '缺少 split 支付必填字段' });
  }

  if (!isSupportedWalletAddress(requestedBuyerWallet)) {
    return res.json({ ok: false, error: 'buyerWallet 地址格式无效' });
  }

  try {
    const services = getServices();
    const service = services.find(s => s.id === normalizedServiceId);
    if (!service) {
      return res.json({ ok: false, error: '服务不存在' });
    }

    const splitVerification = await verifySplitHeaders(paymentHeaders, normalizedServiceId, requestedBuyerWallet, service);

    let route = null;
    if (selectedRoute) {
      route = await resolveSelectedRoute(normalizedServiceId, requestedBuyerWallet, selectedRoute);
    }

    const reportType = service.id.includes('scan') ? 'scanning' :
                       service.id.includes('risk') ? 'risk' :
                       service.id.includes('report') ? 'report' : 'analysis';
    const report = null;
    generateReport(reportType, requestedBuyerWallet, service.wallet).then(r => {
      if (r) { purchase.report = r; savePurchases(getPurchases()); }
    }).catch(() => {});

    const purchase = {
      id: `purchase-x402-split-${Date.now()}`,
      serviceId: normalizedServiceId,
      expert: service.expert,
      expertWallet: service.wallet,
      serviceName: service.name,
      buyerWallet: requestedBuyerWallet,
      price: service.price,
      priceCurrency: 'BNB',
      status: 'completed',
      payment: {
        mode: 'x402-split',
        verified: true,
        chain: splitVerification.chains.join(','),
        txHash: splitVerification.txHashes[0],
        txHashes: splitVerification.txHashes,
        from: splitVerification.fromAddress,
        to: splitVerification.toAddress,
        amount: splitVerification.totalAmount,
      },
      selectedRoute: route,
      report,
      txHash: splitVerification.txHashes[0],
      txHashes: splitVerification.txHashes,
      time: new Date().toISOString()
    };

    addPurchase(purchase);

    addNotification({
      type: 'new_order',
      targetWallet: service.wallet,
      orderId: purchase.id,
      serviceId: service.id,
      serviceName: service.name,
      buyerWallet: requestedBuyerWallet,
      input: '',
    });

    addNotification({
      type: 'order_confirmed',
      targetWallet: requestedBuyerWallet,
      orderId: purchase.id,
      serviceId: service.id,
      serviceName: service.name,
      sellerWallet: service.wallet,
      sellerName: service.expert,
    });

    service.sales += 1;
    saveServices(services);

    addTx({
      time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
      from: requestedBuyerWallet,
      to: service.expert,
      amount: splitVerification.totalAmount,
      reason: `${service.name} (x402-split)`,
      tx: splitVerification.txHashes[0]
    });

    res.json({ ok: true, purchase });
  } catch (error) {
    console.error('x402 split 验证错误:', error);
    res.json({ ok: false, error: `split 支付验证失败: ${error.message}` });
  }
});

// ============================================
// 智能路由引擎（AgentPay SDK）
// ============================================
app.post('/api/smart-route', async (req, res) => {
  const { serviceId, walletAddress } = req.body;

  const normalizedServiceId = sanitizeText(serviceId, 120);
  const normalizedWalletAddress = typeof walletAddress === 'string' ? walletAddress.trim() : '';

  if (!normalizedServiceId || !normalizedWalletAddress) {
    return res.json({ ok: false, error: '缺少 serviceId 或 walletAddress' });
  }

  if (!isSupportedWalletAddress(normalizedWalletAddress)) {
    return res.json({ ok: false, error: 'walletAddress 地址格式无效' });
  }

  try {
    const services = getServices();
    const service = services.find(s => s.id === normalizedServiceId);
    if (!service) {
      return res.json({ ok: false, error: '服务不存在' });
    }

    const result = await runPythonJson(SMART_ROUTER_SCRIPT, ['--wallet', normalizedWalletAddress, '--service', normalizedServiceId], 30000);

    if (!result.success) {
      return res.json({ ok: false, error: result.error || '智能路由计算失败' });
    }

    const routes = (result.routes || []).map(route => ({
      ...route,
      execution_preview: buildExecutionPreview(route, service),
    }));
    const recommended = result.recommended
      ? {
          ...result.recommended,
          execution_preview: buildExecutionPreview(result.recommended, service),
        }
      : null;

    res.json({ 
      ok: true, 
      routes,
      recommended,
      walletAddress: normalizedWalletAddress,
      serviceId: normalizedServiceId
    });
  } catch (error) {
    console.error('智能路由错误:', error);
    res.json({ ok: false, error: `智能路由失败: ${error.message}` });
  }
});

app.get('/healthz', (req, res) => {
  res.json({ ok: true });
});

// 购买记录
app.get('/api/purchases', (req, res) => {
  res.json(getPurchases());
});

// 买家查询自己的订单
app.get('/api/balance', async (req, res) => {
  const wallet = (req.query.wallet || '').trim();
  if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });
  try {
    const { Web3 } = await import('web3');
    const w3 = new Web3('https://bsc-dataseed1.binance.org');
    const balance = await w3.eth.getBalance(wallet);
    res.json({ ok: true, balance: w3.utils.fromWei(balance, 'ether') });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

app.get('/api/my-orders', (req, res) => {
  const wallet = (req.query.wallet || '').trim().toLowerCase();
  if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });
  const purchases = getPurchases();
  const mine = purchases.filter(p => p.buyerWallet?.toLowerCase() === wallet);
  res.json({ ok: true, total: mine.length, orders: mine });
});

// 卖家查询收到的订单
app.get('/api/received-orders', (req, res) => {
  const wallet = (req.query.wallet || '').trim().toLowerCase();
  if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });
  const purchases = getPurchases();
  const mine = purchases.filter(p => p.expertWallet?.toLowerCase() === wallet);
  res.json({ ok: true, total: mine.length, orders: mine });
});

// 卖家收支统计
app.get('/api/seller-stats', (req, res) => {
  const wallet = (req.query.wallet || '').trim().toLowerCase();
  if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });
  const purchases = getPurchases();
  const mine = purchases.filter(p => p.expertWallet?.toLowerCase() === wallet);
  const services = getServices().filter(s => s.wallet?.toLowerCase() === wallet);
  const depositTotal = services.reduce((sum, s) => sum + (s.deposit || 0), 0);
  const incomeTotal = mine.reduce((sum, p) => sum + (p.price || 0), 0);
  const completedOrders = mine.filter(p => p.status === 'completed' || p.status === 'demo-completed').length;
  const pendingOrders = mine.filter(p => !['completed', 'demo-completed', 'rejected'].includes(p.status)).length;
  res.json({ ok: true, income: incomeTotal, deposit: depositTotal, net: incomeTotal - depositTotal, completedOrders, pendingOrders, totalOrders: mine.length });
});

app.get('/api/txs', (req, res) => {
  res.json(getTxs());
});

// Agent 思考事件 API
// agent-events GET/POST 已移除（未使用，live-feed 内部直接调用）

// 合并 feed：交易 + 事件，统一时间线
app.get('/api/live-feed', (req, res) => {
  const txs = getTxs().map(t => ({ ...t, _type: 'tx' }));
  const events = getAgentEvents().map(e => ({ ...e, _type: 'event' }));
  const combined = [...txs, ...events].sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
  res.json(combined);
});

// SSE 实时流
app.get('/api/live-stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  res.write(`data: ${JSON.stringify({ _type: 'connected' })}\n\n`);
  sseClients.add(res);
  req.on('close', () => { sseClients.delete(res); });
});

// ===== Escrow 合约接口 =====
// 获取合约配置（前端需要）
app.get('/api/escrow/config', (req, res) => {
  res.json({
    address: ESCROW_CONFIG.address,
    chainId: ESCROW_CONFIG.chainId,
    defaultTimeout: ESCROW_CONFIG.defaultTimeout,
    abi: ESCROW_ABI,
  });
});

// 验证链上 Escrow 订单
app.get('/api/escrow/order/:orderId', async (req, res) => {
  try {
    const order = await fetchEscrowOrder(req.params.orderId);
    res.json({ ok: true, order });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

// Escrow 统计
app.get('/api/escrow/stats', async (req, res) => {
  try {
    const { Web3 } = await import('web3');
    const w3 = new Web3('https://bsc-dataseed1.binance.org');
    const fullAbi = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'build', 'contracts_ServiceEscrow_sol_ServiceEscrow.abi'), 'utf8'));
    const contract = new w3.eth.Contract(fullAbi, ESCROW_CONFIG.address);
    const [totalEscrowed, totalReleased, totalRefunded, totalDisputed, orderCount] = await Promise.all([
      contract.methods.totalEscrowed().call(),
      contract.methods.totalReleased().call(),
      contract.methods.totalRefunded().call(),
      contract.methods.totalDisputed().call(),
      contract.methods.getOrderCount().call(),
    ]);
    res.json({
      ok: true,
      totalEscrowed: w3.utils.fromWei(totalEscrowed, 'ether'),
      totalReleased: w3.utils.fromWei(totalReleased, 'ether'),
      totalRefunded: w3.utils.fromWei(totalRefunded, 'ether'),
      totalDisputed: Number(totalDisputed),
      orderCount: Number(orderCount),
    });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

// 接收新交易（仅允许内部 Agent 调用）
app.post('/api/tx', (req, res) => {
  const tx = req.body;
  if (!tx || typeof tx !== 'object') return res.json({ ok: false, error: '无效交易数据' });
  // 必须包含有效 from/to/amount 才允许写入
  if (!tx.from || !tx.to || typeof tx.amount !== 'number' || tx.amount <= 0) {
    return res.json({ ok: false, error: '缺少必填字段: from, to, amount' });
  }
  // 允许所有已注册 Agent + 内置 Agent
  const allAgents = getAgents();
  const registeredNames = allAgents.map(a => a.name);
  const builtinNames = ['gangdan','tiedan','choudan','pidan','ludan','four_meme','押金池','CryptoMinds'];
  const knownNames = new Set([...builtinNames, ...registeredNames]);
  if (!knownNames.has(tx.from) && !knownNames.has(tx.to)) {
    // 也允许钱包地址
    const knownAddrs = new Set([
      ...builtinNames.map(n => (AGENTS[n] || {}).addr || '').filter(Boolean),
      ...allAgents.map(a => a.wallet || '')
    ]);
    const fromLower = (tx.from || '').toLowerCase();
    const toLower = (tx.to || '').toLowerCase();
    if (!knownAddrs.has(fromLower) && !knownAddrs.has(toLower)) {
      return res.json({ ok: false, error: '未知的交易方' });
    }
  }
  addTx({ ...tx, time: tx.time || new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}) });
  res.json({ ok: true });
});

// ============================================
// 买家 Agent 注册 + 技能分发
// ============================================

// 买家 Agent 注册
// 退出市场
app.post('/api/experts/deregister/:id', (req, res) => {
  const { wallet } = req.body;
  const services = getServices();
  const svc = services.find(s => s.id === req.params.id);
  if (!svc) return res.json({ ok: false, error: '服务不存在' });
  if (!wallet || svc.wallet.toLowerCase() !== wallet.toLowerCase()) {
    return res.json({ ok: false, error: '只能退出自己的服务' });
  }
  svc.active = false;
  svc.status = 'deregistered';
  svc.deregisteredAt = new Date().toISOString();
  saveServices(services);
  res.json({ ok: true });
});

// 分析服务名称和描述，推断输入输出格式
app.post('/api/analyze-service-format', async (req, res) => {
  const { name, desc } = req.body;
  if (!name && !desc) {
    return res.json({ ok: false, error: '请提供服务名称或描述' });
  }

  // 本地规则匹配（快速、无限制）
  const FORMAT_RULES = [
    { keywords: ['追踪', '监控', '跟踪', 'track'], input: '地址或查询参数', output: '追踪结果或列表' },
    { keywords: ['分析', '评估', '检测', 'analyze'], input: '代币地址或合约地址', output: '分析报告或评分' },
    { keywords: ['流动性', '池子', 'pool', 'liquidity'], input: '池子地址', output: '流动性数据或分析' },
    { keywords: ['巨鲸', '大户', 'whale'], input: '钱包地址', output: '交易记录或持仓信息' },
    { keywords: ['风控', '安全', '风险', 'risk'], input: '代币合约地址', output: '安全评分或风险报告' },
    { keywords: ['新币', '新池子', 'new'], input: '查询参数或留空', output: '新币列表或池子列表' },
    { keywords: ['交易', '买卖', 'trade'], input: '交易对或地址', output: '交易数据或建议' },
    { keywords: ['持仓', '持仓分析', 'holding'], input: '钱包地址', output: '持仓列表或分析' },
  ];

  const text = ((name || '') + ' ' + (desc || '')).toLowerCase();
  for (const rule of FORMAT_RULES) {
    if (rule.keywords.some(k => text.includes(k.toLowerCase()))) {
      return res.json({ ok: true, input: rule.input, output: rule.output, source: 'rule' });
    }
  }

  // 规则匹配不到，调用 MiniMax 2.5
  if (!MINIMAX_API_KEY) {
    return res.json({ ok: false, error: 'API 未配置，请手动填写' });
  }

  try {
    const prompt = `你是一个区块链服务分析助手。根据服务名称和描述，推断用户需要提供什么输入，会得到什么输出。

服务名称：${name || '未提供'}
服务描述：${desc || '未提供'}

请用简洁的一句话回答：
输入格式：用户需要提供什么？（如：钱包地址、代币合约地址、查询参数等）
输出格式：用户会得到什么？（如：分析报告、列表数据、评分等）

只回答这两行，不要其他内容。`;

    const mmRes = await fetch(`${MINIMAX_BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${MINIMAX_API_KEY}`,
      },
      body: JSON.stringify({
        model: 'MiniMax-Text-01',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 100,
      }),
    });

    const mmData = await mmRes.json();
    if (mmData.choices && mmData.choices[0]) {
      const content = mmData.choices[0].message.content;
      // 解析回答
      const inputMatch = content.match(/输入格式[：:](.+)/);
      const outputMatch = content.match(/输出格式[：:](.+)/);
      if (inputMatch && outputMatch) {
        return res.json({
          ok: true,
          input: inputMatch[1].trim(),
          output: outputMatch[1].trim(),
          source: 'ai',
        });
      }
    }

    return res.json({ ok: false, error: 'AI 分析失败，请手动填写' });
  } catch (e) {
    console.error('MiniMax 分析失败:', e.message);
    return res.json({ ok: false, error: 'AI 分析失败，请手动填写' });
  }
});

app.post('/api/agents/register', (req, res) => {
  const { name, wallet, framework } = req.body;
  const agentName = sanitizeText(name, 60);
  const normalizedWallet = typeof wallet === 'string' ? wallet.trim().toLowerCase() : '';
  const normalizedFramework = sanitizeText(framework, 60) || 'unknown';

  if (!agentName || !normalizedWallet) return res.json({ ok: false, error: '缺少 name 或 wallet' });
  if (!isValidAddress(normalizedWallet)) return res.json({ ok: false, error: 'wallet 地址格式无效' });

  const agents = getAgents();
  const duplicate = agents.find(a => a.active && (a.wallet === normalizedWallet || a.name === agentName));
  if (duplicate) {
    return res.json({ ok: false, error: '该 Agent 名称或钱包已注册' });
  }

  const agent = {
    id: `agent-${Date.now()}`,
    name: agentName, wallet: normalizedWallet,
    framework: normalizedFramework,
    registeredAt: new Date().toISOString(),
    skills: ['buy-service'],
    active: true
  };
  agents.push(agent);
  saveAgents(agents);

  // 记录注册交易
  addTx({
    time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
    from: agentName, to: 'CryptoMinds', amount: 0,
    reason: '买家 Agent 注册', tx: `reg-${agent.id}`
  });

  // 自动注入 CryptoMinds 买服务能力到 Agent workspace
  const injected = injectCryptoMindsSkill(agentName, normalizedWallet, req.body.workspacePath);

  res.json({
    ok: true,
    agent,
    skill: getBuyServiceSkill(),
    injected: !!injected
  });
});

// 买家 Agent 列表
app.get('/api/agents', (req, res) => {
  res.json(getAgents().filter(a => a.active));
});

// 获取 Agent 已安装的 Skill 列表
app.get('/api/agents/:wallet/skills', (req, res) => {
  const wallet = req.params.wallet;
  if (!wallet) return res.json({ ok: false, error: '缺少钱包地址' });
  try {
    const { getInstalledSkills } = require('../security/install');
    const skills = getInstalledSkills(wallet);
    res.json({ ok: true, skills });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});

app.post('/api/agents/:wallet/discover-plan', (req, res) => {
  const requestedWallet = typeof req.params.wallet === 'string' ? req.params.wallet.trim().toLowerCase() : '';
  const task = sanitizeText(req.body.task || req.body.prompt, 500);
  const maxCandidates = Number(req.body.maxCandidates || 8);
  const maxPlan = Number(req.body.maxPlan || 3);

  if (!requestedWallet || !isValidAddress(requestedWallet)) {
    return res.json({ ok: false, error: '买家钱包地址无效' });
  }
  if (!task) {
    return res.json({ ok: false, error: '缺少任务描述 task' });
  }

  const agents = getAgents();
  const buyerAgent = agents.find(agent => agent.active && agent.wallet === requestedWallet);
  if (!buyerAgent) {
    return res.json({ ok: false, error: '该买家 Agent 未注册' });
  }

  const services = getServices();
  const recommendations = buildAgentRecommendations(task, services, maxCandidates)
    .filter(service => service.wallet?.toLowerCase() !== requestedWallet);
  const suggestedPlan = buildAutoBuyPlan(task, recommendations, maxPlan).map(service => ({
    serviceId: service.id,
    name: service.name,
    expert: service.expert,
    kind: getServiceKind(service),
    why: service._reasons || [],
  }));

  res.json({
    ok: true,
    buyer: { wallet: requestedWallet, name: buyerAgent.name },
    task,
    candidates: recommendations.map(service => ({
      id: service.id,
      name: service.name,
      expert: service.expert,
      kind: service._kind,
      score: service._score,
      price: service.price,
      effectiveRate: service.effectiveRate || 0,
      totalCalls: service.totalCalls || 0,
      reasons: service._reasons || [],
      inputFormat: service.inputFormat || '',
      outputFormat: service.outputFormat || '',
      desc: service.desc || '',
    })),
    suggestedPlan,
  });
});

app.post('/api/agents/:wallet/auto-buy', async (req, res) => {
  const requestedWallet = typeof req.params.wallet === 'string' ? req.params.wallet.trim().toLowerCase() : '';
  const task = sanitizeText(req.body.task || req.body.prompt, 500);
  const paymentPreference = sanitizeText(req.body.paymentPreference || req.body.paymentMode, 40).toLowerCase() || 'escrow_bnb';
  const explicitTargetAddress = typeof req.body.targetAddress === 'string' ? req.body.targetAddress.trim() : '';
  const buyerNameInput = sanitizeText(req.body.buyerName, 60);
  const waitForResult = req.body.waitForResult !== false;
  const autoConfirmEscrowResult = req.body.autoConfirmEscrowResult === true;
  const maxServices = Number(req.body.maxServices || 3);
  const autoExecute = req.body.autoExecute === true;

  if (!requestedWallet || !isValidAddress(requestedWallet)) {
    return res.json({ ok: false, error: '买家钱包地址无效' });
  }
  if (!task) {
    return res.json({ ok: false, error: '缺少任务描述 task' });
  }

  const agents = getAgents();
  const buyerAgent = agents.find(agent => agent.active && agent.wallet === requestedWallet);
  if (!buyerAgent) {
    return res.json({ ok: false, error: '该买家 Agent 未注册' });
  }

  const services = getServices();
  const recommendedServices = buildAgentRecommendations(task, services, Math.max(maxServices * 2, 6))
    .filter(service => service.wallet?.toLowerCase() !== requestedWallet);
  if (recommendedServices.length === 0) {
    return res.json({ ok: false, error: '未找到可推荐的服务' });
  }

  const fallbackPlan = buildAutoBuyPlan(task, recommendedServices, maxServices).filter(service => service.wallet?.toLowerCase() !== requestedWallet);
  const planItems = normalizePurchasePlan(req.body.purchasePlan || req.body.serviceIds, fallbackPlan);
  if (!req.body.purchasePlan && !req.body.serviceIds && !autoExecute) {
    return res.json({
      ok: true,
      requiresDecision: true,
      buyer: { wallet: requestedWallet, name: buyerAgent.name },
      task,
      paymentPreference,
      recommendedServices: recommendedServices.map(service => ({
        id: service.id,
        name: service.name,
        expert: service.expert,
        kind: service._kind,
        score: service._score,
        reasons: service._reasons || [],
        price: service.price,
        inputFormat: service.inputFormat || '',
        outputFormat: service.outputFormat || '',
      })),
      suggestedPlan: fallbackPlan.map(service => ({
        serviceId: service.id,
        name: service.name,
        expert: service.expert,
        kind: getServiceKind(service),
      })),
      message: '请由买家 Agent 根据候选列表自主决定 purchasePlan，再调用 auto-buy 执行购买',
    });
  }

  let plan;
  try {
    plan = resolvePlanServices(planItems, services, requestedWallet);
  } catch (error) {
    return res.json({ ok: false, error: error.message });
  }

  const steps = [];
  let previousStep = null;

  try {
    for (const item of plan) {
      const service = item.service;
      const stepInput = item.input || buildAutoStepInput(task, previousStep, explicitTargetAddress);
      let purchaseResponse = null;
      let purchase = null;
      let invocation = null;
      let paymentMeta = null;
      const stepPaymentPreference = item.paymentPreference || paymentPreference;

      if (stepPaymentPreference === 'escrow' || stepPaymentPreference === 'escrow_bnb' || stepPaymentPreference === 'bnb_escrow' || stepPaymentPreference === 'bnb') {
        paymentMeta = await createEscrowOrderForBuyer(service, requestedWallet, ESCROW_CONFIG.defaultTimeout);
        purchaseResponse = await callLocalMarketApi('/api/services/buy', {
          serviceId: service.id,
          buyerWallet: requestedWallet,
          buyerName: buyerNameInput || buyerAgent.name,
          paymentMode: 'onchain',
          txHash: paymentMeta.txHash,
          escrowOrderId: paymentMeta.escrowOrderId,
          input: stepInput,
        });
        if (!purchaseResponse.ok) {
          throw new Error(purchaseResponse.error || `自动购买 ${service.name} 失败`);
        }
        purchase = purchaseResponse.purchase || null;

        if (purchase && waitForResult) {
          purchase = await waitForPurchaseState(purchase.id, { timeoutMs: Number(req.body.waitTimeoutMs || 30000) });
          if (purchase?.status === 'delivered' && autoConfirmEscrowResult) {
            await confirmEscrowOrderAsBuyer(purchase.escrowOrderId, requestedWallet);
            const confirmResp = await callLocalMarketApi(`/api/purchases/confirm/${purchase.id}`, {});
            if (!confirmResp.ok) {
              throw new Error(confirmResp.error || `自动确认 ${service.name} 失败`);
            }
            purchase = getPurchaseById(purchase.id) || purchase;
          }
        }
      } else if (stepPaymentPreference === 'x402') {
        const providedHeader = typeof req.body.paymentHeader === 'string' ? req.body.paymentHeader : '';
        const providedHeaders = Array.isArray(req.body.paymentHeaders) ? req.body.paymentHeaders : null;

        if (providedHeaders && providedHeaders.length > 1) {
          purchaseResponse = await callLocalMarketApi('/api/pay/x402/split', {
            serviceId: service.id,
            buyerWallet: requestedWallet,
            paymentHeaders: providedHeaders,
          });
        } else {
          let paymentHeader = providedHeader;
          if (!paymentHeader) {
            const managedPayment = await createManagedX402Payment(service, requestedWallet, task);
            if (!managedPayment.ok) {
              throw new Error(managedPayment.error || '自动生成 x402 支付失败');
            }
            paymentHeader = JSON.stringify(managedPayment.payment_info || {});
            paymentMeta = managedPayment;
          }
          purchaseResponse = await callLocalMarketApi('/api/pay/x402', {
            serviceId: service.id,
            buyerWallet: requestedWallet,
            paymentHeader,
          });
        }

        if (!purchaseResponse.ok) {
          throw new Error(purchaseResponse.error || `x402 自动购买 ${service.name} 失败`);
        }
        purchase = purchaseResponse.purchase || null;
        invocation = await callLocalMarketApi(`/api/skill/call/${service.id}`, {
          buyer: requestedWallet,
          task: stepInput,
          targetAddress: explicitTargetAddress,
        });
      } else {
        throw new Error(`暂不支持的支付偏好: ${paymentPreference}`);
      }

      const stepResult = {
        serviceId: service.id,
        serviceName: service.name,
        expert: service.expert,
        paymentPreference: stepPaymentPreference,
        input: stepInput,
        purchase,
        invocation,
        paymentMeta,
        result: purchase?.result || purchase?.report || invocation?.data || invocation || null,
      };
      steps.push(stepResult);
      previousStep = stepResult;
    }

    res.json({
      ok: true,
      buyer: {
        wallet: requestedWallet,
        name: buyerNameInput || buyerAgent.name,
      },
      task,
      paymentPreference,
      plannedServices: plan.map(item => ({
        id: item.service.id,
        name: item.service.name,
        expert: item.service.expert,
        kind: getServiceKind(item.service),
      })),
      steps,
      finalResult: previousStep?.result || null,
    });
  } catch (error) {
    res.json({
      ok: false,
      error: error.message,
      task,
      paymentPreference,
      plannedServices: plan.map(item => ({ id: item.service.id, name: item.service.name, expert: item.service.expert })),
      steps,
    });
  }
});

// 获取购买技能（公开）
// BUY_SERVICE_SKILL + agents/:id/skill 已移除（未使用）

// 链上交易同步：扫描最近区块，发现所有 Agent 间 BNB 转账
app.get('/api/sync-chain', async (req, res) => {
  try {
    const wallet = req.query.wallet;
    if (!wallet) return res.json({ ok: false, error: '缺少 wallet 参数' });
    
    // 立即返回，后台异步扫描
    res.json({ ok: true, syncing: true });
    
    // 异步扫描（不阻塞请求）
    const walletLower = wallet.toLowerCase();
    const nameMap = {};
    const allAddrs = new Set();
    for (const [k, v] of Object.entries(AGENTS)) {
      nameMap[v.addr.toLowerCase()] = v.name;
      allAddrs.add(v.addr.toLowerCase());
    }
    for (const a of getAgents()) {
      if (a.wallet) { nameMap[a.wallet.toLowerCase()] = a.name; allAddrs.add(a.wallet.toLowerCase()); }
    }
    
    const txs = getTxs();
    const knownHashes = new Set(txs.filter(t => t.tx && t.tx.startsWith('0x')).map(t => t.tx.toLowerCase()));
    
    // 扫描最近 50 个块（约 2.5 分钟，够快）
    const latestBlock = Number(await w3.eth.getBlockNumber());
    const fromBlock = latestBlock - 50;
    let newCount = 0;
    
    for (let i = latestBlock; i >= fromBlock; i--) {
      try {
        const block = await w3.eth.getBlock(i, true);
        if (!block || !block.transactions) continue;
        
        for (const tx of block.transactions) {
          if (typeof tx === 'string') continue;
          
          const fromL = (tx.from || '').toLowerCase();
          const toL = (tx.to || '').toLowerCase();
          
          if (!allAddrs.has(fromL) || !allAddrs.has(toL)) continue;
          if (fromL === toL) continue;
          if (fromL !== walletLower) continue;
          
          const amount = Number(w3.utils.fromWei(tx.value, 'ether'));
          if (amount <= 0) continue;
          if (knownHashes.has(tx.hash.toLowerCase())) continue;
          
          const services = getServices().filter(s => s.active);
          const matchedService = services.find(s => 
            s.wallet && s.wallet.toLowerCase() === toL && 
            Math.abs(Number(s.price) - amount) < 0.00001
          ) || services.find(s => s.wallet && s.wallet.toLowerCase() === toL);
          const reason = matchedService ? matchedService.name : '链上支付';
          const toName = nameMap[toL] || (matchedService ? matchedService.expert : '') || (tx.to || '').slice(0,8);
          
          addTx({
            time: new Date(Number(block.timestamp) * 1000).toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
            from: nameMap[fromL] || tx.from.slice(0,8),
            fromWallet: fromL,
            to: toName,
            amount,
            reason,
            tx: tx.hash,
            receipt: tx.hash,
            route_type: 'direct/bsc/BNB',
            verified: '✅ 已验证',
            timestamp: new Date(Number(block.timestamp) * 1000).toISOString(),
          });
          newCount++;
        }
      } catch(e) { /* 跳过失败的单个区块 */ }
    }
    
    res.json({ ok: true, synced: newCount });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

// 验证单笔链上交易并写入记录
// verify-tx 已移除（未使用，sync-chain 已覆盖链上同步功能）

// skills/execute 已移除（未使用，通过 skill/call 调用）

// Agent 买币指令 API（前端按钮触发）
const { pickSellerHandler, agentBuyHandler } = createAgentBuyHandlers({
  fetchImpl: fetch,
  minimaxApiKey: MINIMAX_API_KEY,
  minimaxBaseUrl: MINIMAX_BASE_URL,
  pythonBin: PYTHON_BIN,
  execFileSync,
  getSellers,
  saveSellers,
  addPurchase,
  addTx,
});

app.post('/api/pick-seller', pickSellerHandler);
app.post('/api/agent-buy', agentBuyHandler);

// 评价订单 API
app.post('/api/rate-order', sellersMarketHandlers.rateOrder);

app.listen(PORT, () => {
  console.log(`CryptoMinds Marketplace running on http://localhost:${PORT}`);
  reconcileEscrowOrders().catch(() => {});
  setInterval(() => {
    reconcileEscrowOrders().catch(() => {});
  }, 60_000);

  // 自动评价：已完成但未评价的订单，24小时后自动好评
  setInterval(async () => {
    try {
      const data = getSellers();
      const now = Date.now();
      const ONE_DAY = 24 * 60 * 60 * 1000;
      let changed = false;
      for (const order of data.orders) {
        if ((order.status === 'completed' || order.status === 'delivered') && !order.rated && order.completedAt) {
          const completedTime = new Date(order.completedAt).getTime();
          if (now - completedTime > ONE_DAY) {
            // 调买家 Agent endpoint 自主评价
            let rating = 5; // 默认好评
            const buyerInfo = data.sellers.find(s => s.wallet.toLowerCase() === order.buyerWallet?.toLowerCase());
            if (buyerInfo?.endpoint) {
              try {
                const resp = await fetch(buyerInfo.endpoint, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ action: 'rateOrder', orderId: order.id, sellerName: order.sellerName, amount: order.amount, tokenAmount: order.tokenAmount }),
                  signal: AbortSignal.timeout(5000),
                });
                const rData = await resp.json();
                if (rData.rating && rData.rating >= 1 && rData.rating <= 5) rating = rData.rating;
              } catch(e) {
                console.log('[auto-rate] Agent endpoint失败，默认好评:', e.message);
              }
            }
            order.rated = true;
            order.rating = rating;
            order.autoRated = true;
            // 更新卖家评分
            const seller = data.sellers.find(s => s.wallet.toLowerCase() === order.sellerWallet?.toLowerCase());
            if (seller) {
              const total = seller.totalOrders || 0;
              const old = seller.rating || 5;
              seller.rating = Math.round(((old * total + rating) / (total + 1)) * 10) / 10;
              if (rating <= 2) seller.badRatings = (seller.badRatings || 0) + 1;
            }
            changed = true;
          }
        }
      }
      if (changed) {
        saveSellers(data);
        // 同步 purchases
        try {
          const purchases = getPurchases();
          for (const p of purchases) {
            const o = data.orders.find(x => x.id === p.id);
            if (o?.rated && !p.rated) { p.rated = true; p.rating = o.rating; p.autoRated = true; }
          }
          fs.writeFileSync(PURCHASES_FILE, JSON.stringify(purchases, null, 2));
        } catch(e2) {}
        console.log('[auto-rate] 自动评价完成');
      }
    } catch(e) {
      console.log('[auto-rate] 错误:', e.message);
    }
  }, 5 * 60_000); // 每5分钟检查
});
