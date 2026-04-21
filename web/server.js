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
const { getEscrowAddress, getEscrowContract, getEscrowStats, checkSellerTimeouts, orderIdToBytes32, escrowABI, deployEscrow } = require('./lib/escrow');

const upload = multer({ dest: '/tmp/cryptominds-uploads/', limits: { fileSize: 100 * 1024 } }); // 100KB max

const app = express();
const { getSellers, saveSellers } = createSellersStore(path.join(__dirname, '..'));
const BSC_RPC = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
const MINIMAX_API_KEY = process.env.MINIMAX_API_KEY || '';
const MINIMAX_BASE_URL = 'https://api.minimaxi.com/v1';
const w3 = new Web3(BSC_RPC);

// Web Push 配置（必须从环境变量读取，不硬编码）
const VAPID_PUBLIC_KEY = process.env.VAPID_PUBLIC_KEY || '';
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY || '';
if (VAPID_PUBLIC_KEY && VAPID_PRIVATE_KEY) {
  webpush.setVapidDetails('mailto:cryptominds@four.meme', VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);
} else {
  console.log('[webpush] VAPID keys not configured, push notifications disabled');
}

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
const DEMO_MODE = process.env.DEMO_MODE === 'true'; // 黑客松评委体验模式
// 押金池地址（获奖后替换为Four.meme地址或合约地址）
const DEPOSIT_POOL_ADDRESS = process.env.DEPOSIT_POOL_ADDRESS || '0x287A44aAADDB78CA67EffCD94E83046353723862';
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const SDK_DIR = path.join(__dirname, '..', 'agentpay_sdk');
const X402_VERIFY_SCRIPT = path.join(SDK_DIR, 'x402_verify.py');
const SMART_ROUTER_SCRIPT = path.join(SDK_DIR, 'smart_router.py');
const MANAGED_X402_SCRIPT = path.join(__dirname, '..', 'scripts', 'managed_x402_payment.py');
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
      route.symbol === 'BNB' ? `直接转账 ${priceLabel} 到卖家钱包` : `向卖家地址发起 ${priceLabel} 支付`,
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
    if (purchase && ['delivered', 'completed', 'rejected'].includes(purchase.status)) {
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
  const sellersData = getSellers(); const services = sellersData.sellers;
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

// 验证 BNB 直接转账：买家 → 卖家钱包
async function verifyPaymentTx(txHash, buyerWallet, service) {
  if (!isValidTxHash(txHash)) return { ok: false, error: 'txHash 格式无效' };
  
  // P3: Demo 模式下跳过真实验证
  if (DEMO_MODE) {
    console.log('[DEMO_MODE] 跳过支付验证:', txHash);
    return {
      ok: true,
      tx: { hash: txHash, from: buyerWallet, to: service.wallet, value: '0', blockNumber: 0, demo: true },
    };
  }
  
  try {
    const tx = await w3.eth.getTransaction(txHash);
    if (!tx) return { ok: false, error: '链上未找到这笔交易' };
    const actualFrom = (tx.from || '').toLowerCase();
    const actualTo = (tx.to || '').toLowerCase();
    const expectedFrom = buyerWallet.toLowerCase();
    const expectedTo = (service.wallet || '').toLowerCase();
    const expectedValueWei = BigInt(w3.utils.toWei(String(service.price), 'ether'));
    const actualValueWei = BigInt(tx.value.toString());
    if (actualFrom !== expectedFrom) return { ok: false, error: '付款地址与 buyerWallet 不一致' };
    if (actualTo !== expectedTo) return { ok: false, error: 'BNB 未发送到卖家钱包' };
    if (actualValueWei < expectedValueWei) return { ok: false, error: '链上支付金额不足' };
    return {
      ok: true,
      tx: { hash: txHash, from: tx.from, to: tx.to, value: tx.value.toString(), blockNumber: Number(tx.blockNumber) },
    };
  } catch (err) {
    return { ok: false, error: `校验 txHash 失败: ${err.message}` };
  }
}

// BNB 直接转账：托管钱包签 BNB → 卖家钱包
async function createDirectPayment(service, buyerWallet) {
  const wallet = findManagedWalletByAddress(buyerWallet);
  if (!wallet?.privateKey || !wallet?.address) {
    throw new Error('买家钱包未托管，无法自动发起支付');
  }
  if (!service.wallet) throw new Error('卖家钱包地址无效');
  const amount = w3.utils.toWei(String(service.price), 'ether');
  const account = w3.eth.accounts.privateKeyToAccount(wallet.privateKey);
  const gasPrice = await w3.eth.getGasPrice();
  const nonce = await w3.eth.getTransactionCount(account.address, 'pending');
  // 动态估算gas：先estimateGas，失败则fallback到30000
  let gasLimit;
  try {
    gasLimit = await w3.eth.estimateGas({
      from: account.address,
      to: service.wallet,
      value: amount,
    });
    gasLimit = Math.ceil(Number(gasLimit) * 1.2); // 加20%缓冲
  } catch (e) {
    console.log('[gas] estimateGas failed, fallback 30000:', e.message);
    gasLimit = 30000;
  }
  const signed = await account.signTransaction({
    from: account.address,
    to: service.wallet,
    value: amount,
    gas: gasLimit,
    gasPrice,
    nonce,
    chainId: 56,
  });
  const receipt = await w3.eth.sendSignedTransaction(signed.rawTransaction);
  return {
    txHash: receipt.transactionHash,
    from: account.address,
    to: service.wallet,
    amount: service.price,
  };
}

// 自由市场——卖家自主入驻，自主定价

// 卖家列表（支持入驻）
// services.json 已废弃，统一使用 sellers.json
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
    const meta = MANAGED_AGENT_META[key] || {
      name: key,
      role: '托管钱包',
      icon: '🤖',
    };
    agents[key] = {
      ...meta,
      addr: wallet.address,
    };
  }
  return agents;
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

// services.json 已废弃，数据统一在 sellers.json

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

  // 兼容旧数据中的 serviceId 映射
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

  const sellersData = getSellers(); const services = sellersData.sellers;
  const service = services.find(item => item.id === purchase.sellerId) || null;
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
    serviceId: purchase.sellerId,
    serviceName: purchase.sellerName,
    sellerWallet: purchase.sellerWallet,
    sellerName: purchase.sellerName,
  });

  return purchase;
}

// 通知卖家 agent：有人付钱了，请用你的模型+策略买币并发回买家钱包
async function attemptAutoDeliverPurchase(purchaseId) {
  const purchases = getPurchases();
  const purchase = purchases.find(item => item.id === purchaseId);
  if (!purchase || purchase.status !== 'pending') return;

  const sellersData = getSellers(); const services = sellersData.sellers;
  const service = services.find(item => item.id === purchase.sellerId && item.active);
  if (!service) return;

  // 通知卖家 agent endpoint
  const sellerEndpoint = service.api?.endpoint || '';
  if (!sellerEndpoint) {
    console.log('[notify-seller] 无 endpoint，跳过通知:', service.id);
    return;
  }

  try {
    const notifyPayload = {
      action: 'new_order',
      orderId: purchase.id,
      serviceId: service.id,
      buyerWallet: purchase.buyerWallet,
      buyerName: purchase.buyerName,
      amount: purchase.price,
      currency: 'BNB',
      input: purchase.input || '',
      txHash: purchase.txHash || '',
    };
    const resp = await fetch(sellerEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(notifyPayload),
      signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) throw new Error(`卖家 endpoint 返回 ${resp.status}`);
    const data = await resp.json().catch(() => ({}));
    console.log('[notify-seller] 通知成功:', purchase.id, data);
  } catch (error) {
    console.error('[notify-seller] 通知失败:', error.message);
    addNotification({
      type: 'manual_delivery_required',
      targetWallet: purchase.sellerWallet,
      orderId: purchase.id,
      serviceId: purchase.sellerId,
      serviceName: purchase.sellerName,
      buyerWallet: purchase.buyerWallet,
      buyerName: purchase.buyerName,
      reason: error.message,
    });
  }
}

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// CORS — 允许 SDK / 外部 Agent 跨域调用
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-402-Payment');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// TX 记录
const TX_LOG = path.join(__dirname, '..', 'tx-log.json');
const AGENT_EVENTS_FILE = path.join(__dirname, '..', 'agent_events.json');

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
  const entries = Object.entries(getManagedAgents());
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
    for (const key of Object.keys(getManagedAgents())) fallback[key] = '0';
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
  totalSpent = txs.reduce((sum, tx) => sum + Number(tx.amount || 0), 0);
  const sellersData = getSellers();
  const activeSellers = sellersData.sellers.filter(s => s.active !== false);
  const pendingSellers = sellersData.sellers.filter(s => s.serviceStatus === 'pending');
  res.render('index', { AGENTS: getManagedAgents(), activeSellers, pendingSellers, TRANSACTIONS: txs, balances, totalSpent: totalSpent.toFixed(4), txCount, DEMO_MODE });
});

app.get('/api/balances', async (req, res) => {
  const balances = await getBalancesCached(false);
  // 后台异步刷新
  getBalancesCached(true);
  const result = {};
  for (const [key, agent] of Object.entries(getManagedAgents())) {
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
  const services = getSellers().sellers.filter(s => s.active && s.status === 'approved');
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

// P3: Demo 模式状态（黑客松评委体验）
app.get('/api/config', (req, res) => {
  res.json({
    ok: true,
    demoMode: DEMO_MODE,
    demoWallet: DEMO_WALLET,
    port: PORT,
    chain: 'BSC',
  });
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

// 提交服务结果（卖家调用）
app.post('/api/orders/:orderId/result', async (req, res) => {
  const { orderId } = req.params;
  const { output, sellerWallet, deliveryTxHash } = req.body;

  if (!orderId || !output || !sellerWallet) {
    return res.json({ ok: false, error: '缺少 orderId, output 或 sellerWallet' });
  }

  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === orderId);
  if (!purchase) {
    return res.json({ ok: false, error: '订单不存在' });
  }

  if (purchase.sellerWallet?.toLowerCase() !== sellerWallet.toLowerCase()) {
    return res.json({ ok: false, error: '只有卖家能提交结果' });
  }
  if (purchase.status !== 'pending') {
    return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法提交结果` });
  }

  try {
    // 如果订单走合约托管，调用合约 deliver()
    if (purchase.escrowOrderId) {
      const { getEscrowContract, orderIdToBytes32 } = require('./lib/escrow');
      const contract = getEscrowContract();
      if (contract) {
        const b32 = orderIdToBytes32(purchase.escrowOrderId);
        // 注意：合约 deliver() 需要 seller 签名，这里只记录，前端负责调合约
        console.log(`[escrow] 订单 ${orderId} 有合约托管，escrowOrderId: ${purchase.escrowOrderId}`);
      }
    }

    await markPurchaseDelivered(orderId, output, {
      autoDelivered: false,
      rawOutput: output,
      deliveryTxHash: deliveryTxHash || '',
    });
    res.json({ ok: true, escrowOrderId: purchase.escrowOrderId || null });
  } catch (err) {
    res.json({ ok: false, error: err.message });
  }
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


// 卖家入驻
app.get('/api/config/deposit', (req, res) => {
  res.json({
    depositPoolAddress: DEPOSIT_POOL_ADDRESS,
    stakingAddress: DEPOSIT_POOL_ADDRESS,
    isOnChain: DEPOSIT_POOL_ADDRESS !== '0x0000000000000000000000000000000000000000'
  });
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
    const rating = Number(req.body.rating || 5);
    purchase.status = 'completed';
    purchase.autoConfirmed = req.body.auto === true || req.body.rating !== undefined;
    purchase.confirmedAt = new Date().toISOString();
    purchase.rating = rating;
    if (req.body.comment) purchase.comment = req.body.comment;
    savePurchases(purchases);

    // 更新卖家评分+权重
    const data = getSellers();
    const seller = data.sellers?.find(s => s.wallet?.toLowerCase() === purchase.sellerWallet?.toLowerCase());
    if (seller) {
      const totalRatings = seller.totalOrders || 0;
      const oldAvg = seller.rating || 5;
      seller.rating = Math.round(((oldAvg * totalRatings + rating) / (totalRatings + 1)) * 10) / 10;
      seller.totalOrders = totalRatings + 1;
      seller.weight = calculateWeight(seller);
      if (rating <= 2) seller.badRatings = (seller.badRatings || 0) + 1;
      saveSellers(data);

      // 通知卖家Agent订单已确认
      if (seller.endpoint) {
        try {
          await fetch(seller.endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              event: 'order_confirmed',
              orderId: purchase.id,
              rating,
              comment: req.body.comment || '',
            }),
          });
        } catch (e) {
          console.error('[confirm] 通知卖家Agent失败:', e.message);
        }
      }
    }

    addTx({
      time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
      from: purchase.buyerName || '未知',
      fromWallet: purchase.buyerWallet,
      to: purchase.sellerName || '卖家',
      amount: purchase.price,
      reason: `${purchase.sellerName} [确认购买]`,
      tx: purchase.txHash || purchase.id,
      verified: '✅ 已验证',
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
  if (purchase.status !== 'delivered' && purchase.status !== 'pending_confirm') return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法拒绝` });

  purchase.status = 'rejected';
  purchase.rejectedAt = new Date().toISOString();
  savePurchases(purchases);

  res.json({ ok: true, purchase });
});

// 卖家超时退款
app.post('/api/orders/:orderId/refund', async (req, res) => {
  const { reason, txHash } = req.body;
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === req.params.orderId);
  if (!purchase) return res.json({ ok: false, error: '订单不存在' });

  purchase.status = 'seller_timeout';
  purchase.refundReason = reason || 'seller_timeout';
  purchase.refundTxHash = txHash;
  purchase.refundedAt = new Date().toISOString();
  // 注意：这里不自动扣减卖家余额，押金仍归平台；退款为平台代退处理
  savePurchases(purchases);

  // 记录转账流水
  try {
    addTx({
      time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
      from: 'Escrow',
      fromWallet: 'Escrow',
      to: purchase.buyerWallet,
      amount: purchase.price,
      reason: `卖家超时退款 ${reason || 'seller_timeout'}`,
      tx: txHash,
      verified: '✅ 已退款',
      receipt: purchase.id,
    });
  } catch (e) {
    console.error('[refund-tx] 记录转账失败:', e.message);
  }

  res.json({ ok: true, purchase });
});

// 获取待确认订单列表
app.get('/api/purchases/pending', (req, res) => {
  const purchases = getPurchases();
  const pending = purchases.filter(p => p.status === 'delivered' || p.status === 'pending_confirm');
  res.json({ ok: true, count: pending.length, purchases: pending });
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


// ===== V2 API =====
const sellersMarketHandlers = createSellersMarketHandlers({
  getSellers,
  saveSellers,
  getPurchases,
  savePurchases,
  purchasesFile: PURCHASES_FILE,
  addTx,
  pythonBin: PYTHON_BIN,
  execFileSync,
  w3,
  depositPoolAddress: DEPOSIT_POOL_ADDRESS,
  demoMode: DEMO_MODE,
});
const { calculateWeight } = sellersMarketHandlers;

app.get('/api/sellers', sellersMarketHandlers.listSellers);
app.post('/api/sellers/register', sellersMarketHandlers.registerSeller);
app.post('/api/sellers/:wallet/deposit', sellersMarketHandlers.depositSeller);
app.post('/api/orders/:id/execute', sellersMarketHandlers.executeOrder);
app.post('/api/orders/create', sellersMarketHandlers.createOrder);
app.post('/api/sellers/exit', sellersMarketHandlers.exitSeller);
app.post('/api/sellers/:wallet/refund', sellersMarketHandlers.adminRefundSeller);





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
    const servicesJson = JSON.stringify(getSellers().sellers);
    const result = await runPythonJson(X402_VERIFY_SCRIPT, [paymentHeader, normalizedServiceId, servicesJson]);

    if (!result.valid) {
      return res.json({ ok: false, error: result.error || '支付验证失败' });
    }

    // 验证成功，执行服务
    const sellersData = getSellers(); const services = sellersData.sellers;
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
      sellerName: service.expert,
      sellerWallet: service.wallet,
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
    saveSellers(sellersData);

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
    const sellersData = getSellers(); const services = sellersData.sellers;
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
      sellerName: service.expert,
      sellerWallet: service.wallet,
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
    saveSellers(sellersData);

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
    const sellersData = getSellers(); const services = sellersData.sellers;
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
  const mine = purchases.filter(p => (p.sellerWallet || p.expertWallet)?.toLowerCase() === wallet);
  res.json({ ok: true, total: mine.length, orders: mine });
});

// 兼容旧测试/旧前端的卖家订单查询接口
app.get('/api/orders', (req, res) => {
  const wallet = (req.query.wallet || req.query.sellerWallet || '').trim().toLowerCase();
  if (!wallet) {
    return res.json({ ok: false, error: '缺少 wallet' });
  }
  const purchases = getPurchases();
  const mine = purchases.filter(p => (p.sellerWallet || p.expertWallet)?.toLowerCase() === wallet);
  res.json({ ok: true, total: mine.length, orders: mine });
});

// 卖家收支统计
app.get('/api/seller-stats', (req, res) => {
  const wallet = (req.query.wallet || '').trim().toLowerCase();
  if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });
  const purchases = getPurchases();
  const mine = purchases.filter(p => (p.sellerWallet || p.expertWallet)?.toLowerCase() === wallet);
  const services = getSellers().sellers.filter(s => s.wallet?.toLowerCase() === wallet);
  const depositTotal = services.reduce((sum, s) => sum + (s.deposit || 0), 0);
  const incomeTotal = mine.reduce((sum, p) => sum + (p.price || 0), 0);
  const completedOrders = mine.filter(p => p.status === 'completed').length;
  const pendingOrders = mine.filter(p => !['completed', 'rejected'].includes(p.status)).length;
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
  const managedAgents = getManagedAgents();
  const builtinNames = ['押金池', 'CryptoMinds', ...Object.keys(managedAgents), ...Object.values(managedAgents).map(agent => agent.name)];
  const knownNames = new Set([...builtinNames, ...registeredNames]);
  if (!knownNames.has(tx.from) && !knownNames.has(tx.to)) {
    // 也允许钱包地址
    const knownAddrs = new Set([
      ...Object.values(managedAgents).map(agent => agent.addr || '').filter(Boolean),
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

  // endpoint: 买家Agent的API地址，有则自有大脑决策，无则走平台MiniMax
  const endpoint = typeof req.body.endpoint === 'string' ? req.body.endpoint.trim() : '';
  const agent = {
    id: `agent-${Date.now()}`,
    name: agentName, wallet: normalizedWallet,
    framework: normalizedFramework,
    endpoint, // 自有API模式：填了就有，没填=平台托管
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
// /api/agents/:wallet/skills — DEPRECATED (旧Skill概念已废弃)

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

  const sellersData = getSellers(); const services = sellersData.sellers;
  const recommendations = buildAgentRecommendations(task, services, maxCandidates)
    .filter(service => service.wallet?.toLowerCase() !== requestedWallet);
  const suggestedPlan = buildAutoBuyPlan(task, recommendations, maxPlan).map(service => ({
    serviceId: service.id,
    name: service.name,
    sellerName: service.expert,
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
      sellerName: service.expert,
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
  const paymentPreference = sanitizeText(req.body.paymentPreference || req.body.paymentMode, 40).toLowerCase() || 'direct_bnb';
  const explicitTargetAddress = typeof req.body.targetAddress === 'string' ? req.body.targetAddress.trim() : '';
  const buyerNameInput = sanitizeText(req.body.buyerName, 60);
  const waitForResult = req.body.waitForResult !== false;
  const autoConfirmResult = req.body.autoConfirmResult === true;
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

  const sellersData = getSellers(); const services = sellersData.sellers;
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
        sellerName: service.expert,
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
        sellerName: service.expert,
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
    if (!plan || plan.length === 0) {
      return res.json({ ok: false, error: 'plan 为空，无法执行购买', planItems, fallbackPlan });
    }
    for (const item of plan) {
      const service = item.service;
      const stepInput = item.input || buildAutoStepInput(task, previousStep, explicitTargetAddress);
      let purchaseResponse = null;
      let purchase = null;
      let invocation = null;
      let paymentMeta = null;
      const stepPaymentPreference = item.paymentPreference || paymentPreference;

      if (stepPaymentPreference === 'direct_bnb' || stepPaymentPreference === 'bnb') {
        // 直接 BNB 转账：托管钱包签 BNB → 卖家钱包
        console.log('[auto-buy] 开始创建直接支付, service:', service.id, 'buyer:', requestedWallet);
        paymentMeta = await createDirectPayment(service, requestedWallet);
        console.log('[auto-buy] 支付完成, txHash:', paymentMeta.txHash);
        purchaseResponse = await callLocalMarketApi('/api/orders/create', {
          serviceId: service.id,
          buyerWallet: requestedWallet,
          buyerName: buyerNameInput || buyerAgent.name,
          paymentMode: 'direct_bnb',
          txHash: paymentMeta.txHash,
          input: stepInput,
        });
        if (!purchaseResponse.ok) {
          throw new Error(purchaseResponse.error || `自动购买 ${service.name} 失败`);
        }
        purchase = purchaseResponse.purchase || null;

        if (purchase && waitForResult) {
          purchase = await waitForPurchaseState(purchase.id, { timeoutMs: Number(req.body.waitTimeoutMs || 60000) });
          // 卖家交付后自动确认评分
          if (purchase?.status === 'delivered' && !purchase.autoConfirmed) {
            const confirmResp = await callLocalMarketApi(`/api/purchases/confirm/${purchase.id}`, {
              rating: 5,
              comment: '自动确认',
            });
            if (!confirmResp.ok) {
              console.error('自动确认失败:', confirmResp.error);
            } else {
              purchase = getPurchaseById(purchase.id) || purchase;
            }
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
        // 通知卖家Agent执行（平台不代执行）
        invocation = await callLocalMarketApi(`/api/orders/${purchase.id}/execute`, {
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
        sellerName: service.expert,
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
        sellerName: item.service.expert,
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
      plannedServices: plan.map(item => ({ id: item.service.id, name: item.service.name, sellerName: item.service.expert })),
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
    for (const [k, v] of Object.entries(getManagedAgents())) {
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
          
          const services = getSellers().sellers.filter(s => s.active);
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
  getAgents,
  addPurchase,
  addTx,
});

app.post('/api/pick-seller', pickSellerHandler);
app.post('/api/agent-buy', agentBuyHandler);

// 评价订单 API
app.post('/api/rate-order', sellersMarketHandlers.rateOrder);

// 管理员权限检查（避免前端硬编码钱包地址）
app.get('/api/admin-check', (req, res) => {
  const adminWallets = (process.env.ADMIN_WALLETS || '').split(',').filter(Boolean);
  const buyerWallet = req.query.wallet || '';
  const isAdmin = adminWallets.some(w => w.toLowerCase() === buyerWallet.toLowerCase());
  res.json({ isAdmin });
});

// ══════════════════════════════════════════════════════
// Escrow 担保合约 API
// ══════════════════════════════════════════════════════

// 获取合约信息（地址+ABI+统计）
app.get('/api/escrow/info', (req, res) => {
  const addr = getEscrowAddress();
  if (!addr) return res.json({ ok: false, error: '合约未部署' });
  res.json({
    ok: true,
    address: addr,
    abi: escrowABI,
  });
});

// 获取合约统计数据
app.get('/api/escrow/stats', async (req, res) => {
  const stats = await getEscrowStats();
  if (!stats) return res.json({ ok: false, error: '合约未部署' });
  res.json({ ok: true, ...stats });
});

// 查询链上订单状态
app.get('/api/escrow/order/:orderId', async (req, res) => {
  const { getOrderFromChain } = require('./lib/escrow');
  const order = await getOrderFromChain(req.params.orderId);
  if (!order) return res.json({ ok: false, error: '订单未找到' });
  res.json({ ok: true, order });
});

// 部署合约（管理员）
app.post('/api/escrow/deploy', async (req, res) => {
  const adminWallets = (process.env.ADMIN_WALLETS || '').split(',').filter(Boolean);
  const caller = req.body.caller || '';
  if (!adminWallets.some(w => w.toLowerCase() === caller.toLowerCase())) {
    return res.json({ ok: false, error: '无管理员权限' });
  }
  const deployerKey = process.env.DEPLOYER_PRIVATE_KEY;
  if (!deployerKey) return res.json({ ok: false, error: '未配置 DEPLOYER_PRIVATE_KEY' });
  try {
    const addr = await deployEscrow(deployerKey);
    res.json({ ok: true, address: addr });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});

app.listen(PORT, () => {
  console.log(`CryptoMinds Marketplace running on http://localhost:${PORT}`);
  const escrowAddr = getEscrowAddress();
  if (escrowAddr) {
    console.log(`[escrow] 合约地址: ${escrowAddr}`);
  } else {
    console.log('[escrow] 合约未部署，Escrow 功能不可用');
  }

  // 卖家超时检查 — 每2分钟扫描一次
  setInterval(async () => {
    try {
      await checkSellerTimeouts(getSellers, saveSellers);
    } catch (e) {
      console.error('[escrow-timeout] 检查失败:', e.message);
    }
  }, 2 * 60_000);

  // 自动评价：已完成但未评价的订单，24小时后自动好评
  setInterval(async () => {
    try {
      const data = getSellers();
      const now = Date.now();
      const ONE_DAY = 24 * 60 * 60 * 1000;
      let changed = false;
      for (const order of data.orders) {
        // 自动确认：delivered 24小时未确认 → 自动确认
        if (order.status === 'delivered' && order.deliveredAt && !order.confirmedAt) {
          const deliveredTime = new Date(order.deliveredAt).getTime();
          if (now - deliveredTime > ONE_DAY) {
            order.status = 'completed';
            order.confirmedAt = new Date().toISOString();
            order.autoConfirmed = true;
            changed = true;
            // 通知卖家Agent
            const seller = data.sellers.find(s => s.wallet.toLowerCase() === order.sellerWallet?.toLowerCase());
            if (seller?.endpoint) {
              try {
                await fetch(seller.endpoint, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ event: 'order_confirmed', orderId: order.id, rating: 0, autoConfirmed: true }),
                });
              } catch(e) { console.log('[auto-confirm] 通知卖家失败:', e.message); }
            }
          }
        }
        // 自动评价：completed/delivered 24小时未评价 → 自动评价
        if ((order.status === 'completed' || order.status === 'delivered') && !order.rated && order.completedAt) {
          const completedTime = new Date(order.completedAt).getTime();
          if (now - completedTime > ONE_DAY) {
            let rating = 5;
            const buyerAgent = getAgents().find(a => a.active && a.wallet.toLowerCase() === order.buyerWallet?.toLowerCase());
            if (buyerAgent?.endpoint) {
              try {
                const resp = await fetch(buyerAgent.endpoint, {
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
            const seller = data.sellers.find(s => s.wallet.toLowerCase() === order.sellerWallet?.toLowerCase());
            if (seller) {
              const total = seller.totalOrders || 0;
              const old = seller.rating || 5;
              seller.rating = Math.round(((old * total + rating) / (total + 1)) * 10) / 10;
              seller.weight = calculateWeight(seller);
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

// ── 进程异常保护 ──────────────────────────────────────────
process.on('uncaughtException', (err) => {
  console.error('[FATAL] Uncaught Exception:', err.message);
  // 不退出，让服务继续运行（黑客松Demo不能崩）
});
process.on('unhandledRejection', (reason) => {
  console.error('[WARN] Unhandled Rejection:', reason);
});
