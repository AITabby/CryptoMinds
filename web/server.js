const express = require('express');
const { Web3 } = require('web3');
const path = require('path');
const fs = require('fs');
const { execFile, spawn } = require('child_process');
const dns = require('dns').promises;
const net = require('net');
const multer = require('multer');
const { injectCryptoMindsSkill } = require('./inject_skill');

const upload = multer({ dest: '/tmp/cryptominds-uploads/', limits: { fileSize: 100 * 1024 } }); // 100KB max

const app = express();
const BSC_RPC = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
const w3 = new Web3(BSC_RPC);

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

const PORT = 3456;
const DEMO_WALLET = '0xd2f899ce74320aef9d8f2359183232a554f4c0e1';
// 押金池地址（获奖后替换为Four.meme地址或合约地址）
const DEPOSIT_POOL_ADDRESS = process.env.DEPOSIT_POOL_ADDRESS || '0x698373a42c8ed23733b30c505ec48c253ced9792';
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const SDK_DIR = path.join(__dirname, '..', 'agentpay_sdk');
const X402_VERIFY_SCRIPT = path.join(SDK_DIR, 'x402_verify.py');
const SMART_ROUTER_SCRIPT = path.join(SDK_DIR, 'smart_router.py');

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
      `向服务提供者地址发起 ${priceLabel} 直付`,
      '提交 x402 支付头并验证链上交易',
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
  if (!isValidTxHash(txHash)) {
    return { ok: false, error: 'txHash 格式无效' };
  }

  try {
    const receipt = await w3.eth.getTransactionReceipt(txHash);
    const tx = await w3.eth.getTransaction(txHash);

    if (!receipt || !tx) return { ok: false, error: '链上未找到这笔交易' };
    if (Number(receipt.status) !== 1) return { ok: false, error: '链上交易执行失败' };
    if (!tx.to) return { ok: false, error: '交易缺少接收地址' };

    const expectedTo = service.wallet.toLowerCase();
    const actualTo = tx.to.toLowerCase();
    const actualFrom = tx.from.toLowerCase();
    const expectedFrom = buyerWallet.toLowerCase();
    const expectedValueWei = BigInt(w3.utils.toWei(String(service.price), 'ether'));
    const actualValueWei = BigInt(tx.value.toString());

    if (actualTo !== expectedTo) {
      return { ok: false, error: '收款地址不匹配服务提供者' };
    }
    if (actualFrom !== expectedFrom) {
      return { ok: false, error: '付款地址不匹配 buyerWallet' };
    }
    if (actualValueWei < expectedValueWei) {
      return { ok: false, error: '链上支付金额不足' };
    }

    return {
      ok: true,
      tx: {
        hash: tx.hash,
        from: tx.from,
        to: tx.to,
        valueWei: tx.value.toString(),
        valueBnb: w3.utils.fromWei(tx.value.toString(), 'ether'),
        blockNumber: receipt.blockNumber,
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

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// TX 记录
const TX_LOG = path.join(__dirname, '..', 'tx-log.json');
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
  if (txs.length > 50) txs.length = 50;
  fs.writeFileSync(TX_LOG, JSON.stringify(txs, null, 2));
}

let balanceCache = { data: {}, fetchedAt: 0 };

async function fetchBalancesLive() {
  const result = {};
  for (const [key, agent] of Object.entries(AGENTS)) {
    const bal = await w3.eth.getBalance(agent.addr);
    result[key] = w3.utils.fromWei(bal.toString(), 'ether');
  }
  return result;
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
  const balances = await getBalancesCached(true);
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
  const bnbPrice = await fetchBnbPrice();
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

  purchase.result = output;
  purchase.resultAt = new Date().toISOString();
  purchase.status = 'delivered';
  savePurchases(purchases);

  // 通知买家：结果已出
  addNotification({
    type: 'order_result',
    targetWallet: purchase.buyerWallet,
    orderId: purchase.id,
    serviceId: purchase.serviceId,
    serviceName: purchase.serviceName,
    sellerWallet: purchase.expertWallet,
    sellerName: purchase.expert,
  });

  res.json({ ok: true });
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

app.post('/api/experts/register', upload.none(), async (req, res) => {
  const { expert, wallet, name, desc, price, deposit, depositTx, inputFormat, outputFormat, latency } = req.body;
  const expertName = sanitizeText(expert, 40);
  const skillName = sanitizeText(name, 80);
  const description = sanitizeText(desc, 240);
  const normalizedWallet = typeof wallet === 'string' ? wallet.trim() : '';
  const parsedPrice = parsePositiveNumber(price);
  const parsedDeposit = parseNonNegativeNumber(deposit, 0.001);
  const depositTxHash = typeof depositTx === 'string' ? depositTx.trim() : '';
  // 不再需要框架筛选（服务契约模式）

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
  // 服务契约（不再上传文件）
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

  // 无需安全扫描（不再上传文件，服务契约模式）
  let securityScan = { level: 'safe', score: 100, issues: [], summary: '✅ 服务契约模式' };

  const id = `${expertName}-${skillName.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}`;
  // 入驻后需审核

  const newService = {
    id, expert: expertName, wallet: normalizedWallet, service: 'service', name: skillName,
    desc: description || '', price: parsedPrice, deposit: parsedDeposit,
    inputFormat: inputFmt, outputFormat: outputFmt, latency: latencyEst || '',
    api: { endpoint: '', method: 'POST' },
    depositTx: depositTxHash || null,
    security: { level: 'safe', score: 100, summary: '✅ 服务契约模式' },
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
    const depositAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
    if (depositAmount < 0.001) {
      return res.json({ ok: false, error: '押金金额不足' });
    }
    
    svc.status = 'pending'; // 更新为待审核
    svc.depositTx = txHash;
    svc.wallet = tx.from.toLowerCase(); // 用实际付款钱包
    saveServices(services);
    
    addTx({ time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}), from: svc.expert, to: '押金池', amount: depositAmount, reason: `入驻: ${svc.name}`, tx: txHash });
    res.json({ ok: true });
  } catch(e) {
    res.json({ ok: false, error: '交易验证失败: ' + e.message });
  }
});

// 确认购买（待确认订单 → 完成）
app.post('/api/purchases/confirm/:purchaseId', (req, res) => {
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === req.params.purchaseId);
  if (!purchase) return res.json({ ok: false, error: '订单不存在' });
  if (purchase.status !== 'pending_confirm') return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法确认` });

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
});

// 拒绝购买（待确认订单 → 取消）
app.post('/api/purchases/reject/:purchaseId', (req, res) => {
  const purchases = getPurchases();
  const purchase = purchases.find(p => p.id === req.params.purchaseId);
  if (!purchase) return res.json({ ok: false, error: '订单不存在' });
  if (purchase.status !== 'pending_confirm') return res.json({ ok: false, error: `订单状态为 ${purchase.status}，无法拒绝` });

  purchase.status = 'rejected';
  purchase.rejectedAt = new Date().toISOString();
  savePurchases(purchases);

  res.json({ ok: true, purchase });
});

// 获取待确认订单列表
app.get('/api/purchases/pending', (req, res) => {
  const purchases = getPurchases();
  const pending = purchases.filter(p => p.status === 'pending_confirm');
  res.json({ ok: true, count: pending.length, purchases: pending });
});

// 专家退出（退还押金）
app.post('/api/experts/exit', (req, res) => {
  const { expert, serviceId } = req.body;
  if (!expert) return res.json({ ok: false, error: '缺少专家名' });
  const services = getServices();
  const idx = services.findIndex(s => serviceId ? s.id === serviceId : s.expert === expert);
  if (idx === -1) return res.json({ ok: false, error: '未找到该专家' });
  const svc = services[idx];
  if (!svc.active) return res.json({ ok: false, error: '已退出' });

  // 检查是否有未完成的订单
  const purchases = getPurchases();
  const pending = purchases.filter(p => p.expert === expert && p.status === 'pending');
  if (pending.length > 0) return res.json({ ok: false, error: `有 ${pending.length} 笔订单未完成，无法退出` });

  svc.active = false;
  svc.exitedAt = new Date().toISOString();
  svc.refunded = true;
  services[idx] = svc;
  saveServices(services);

  // 记录退还交易
  addTx({
    time: new Date().toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
    from: '押金池', to: expert, amount: svc.deposit || 0.001,
    reason: `退出退还押金`, tx: `exit-${svc.id}`
  });

  res.json({ ok: true, message: `已退出，退还押金 ${(svc.deposit || 0.001)} BNB`, service: svc });
});

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

// 审核日志（公开只读）
app.get('/api/admin/audit-log', (req, res) => {
  const services = getServices();
  const approved = services.filter(s => s.status === 'approved' || (s.active && !s.status));
  const rejected = services.filter(s => s.status === 'rejected');
  const pending = services.filter(s => s.status === 'pending');
  res.json({ ok: true, approved, rejected, pending });
});

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

// 购买服务
app.post('/api/services/buy', async (req, res) => {
  const { serviceId, buyerWallet, buyerName, txHash, selectedRoute, paymentMode } = req.body;
  const normalizedServiceId = sanitizeText(serviceId, 120);
  const normalizedBuyerWallet = typeof buyerWallet === 'string' ? buyerWallet.trim() : '';
  const normalizedPaymentMode = typeof paymentMode === 'string' ? paymentMode.trim().toLowerCase() : '';
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
    const verification = await verifyPaymentTx(txHash, normalizedBuyerWallet, service);
    if (!verification.ok) {
      return res.json({ ok: false, error: verification.error });
    }
    payment = {
      mode: 'onchain',
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
    status: autoConfirm ? (payment.verified ? 'completed' : 'demo-completed') : 'pending_confirm',
    payment,
    selectedRoute: route,
    report,
    txHash: txHash || '',
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

  // 通知买家：订单已确认
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
    // 待确认模式：等待人工确认
    res.json({ ok: true, purchase, needConfirm: true, message: '购买请求已提交，等待确认' });
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

app.get('/api/txs', (req, res) => {
  res.json(getTxs());
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

// 获取购买技能（公开）
const BUY_SERVICE_SKILL = {
  name: 'buy-service',
  version: '1.0',
  description: '从 CryptoMinds 市场购买专家服务，获取链上情报',
  marketApi: 'http://localhost:3456',
  steps: [
    { action: 'discover', method: 'GET', path: '/api/market', desc: '查看可用服务列表' },
    { action: 'purchase', method: 'POST', path: '/api/services/buy', desc: '购买服务并获取 Skill 执行结果', body: { serviceId: '服务ID', buyerWallet: '你的钱包地址', buyerName: '你的名字' } },
    { action: 'read-report', desc: '解析返回的 report 字段，包含专家提供的数据和建议' }
  ],
  reportTypes: {
    scanning: 'Skill 执行结果 — 推荐代币 + 价格 + 风险',
    risk: '风控分析 — 合约检查 + 安全结论',
    report: '持有建议 — 持仓分析 + 买卖建议',
    analysis: '深度分析 — 综合数据'
  },
  quickStart: 'GET /api/market 查看服务 → POST /api/services/buy 购买 → 拿到 report 决策'
};

function getBuyServiceSkill() {
  return BUY_SERVICE_SKILL;
}

// 获取购买技能（公开接口）
app.get('/api/skill/buy-service', (req, res) => {
  res.json(BUY_SERVICE_SKILL);
});

// 指定 Agent 获取技能
app.get('/api/agents/:id/skill', (req, res) => {
  const agents = getAgents();
  const agent = agents.find(a => a.id === req.params.id);
  if (!agent) return res.json({ ok: false, error: 'Agent 不存在' });
  res.json({ ok: true, agent: agent.name, skill: BUY_SERVICE_SKILL });
});

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
app.get('/api/verify-tx/:txHash', async (req, res) => {
  try {
    const txHash = req.params.txHash;
    if (!txHash || !txHash.startsWith('0x')) return res.json({ ok: false, error: '无效交易哈希' });
    
    // 检查是否已记录
    const txs = getTxs();
    if (txs.find(t => t.tx && t.tx.toLowerCase() === txHash.toLowerCase())) {
      return res.json({ ok: true, existed: true });
    }
    
    // 从链上查交易
    const tx = await w3.eth.getTransaction(txHash);
    if (!tx) return res.json({ ok: false, error: '链上未找到交易' });
    
    const receipt = await w3.eth.getTransactionReceipt(txHash);
    if (!receipt || receipt.status !== 1n) return res.json({ ok: false, error: '交易未确认或失败' });
    
    // 检查是否是 Agent 间转账
    const fromLower = tx.from.toLowerCase();
    const toLower = tx.to ? tx.to.toLowerCase() : '';
    const agentAddrs = Object.values(AGENTS).map(a => a.addr.toLowerCase());
    const registered = getAgents();
    const registeredAddrs = registered.map(a => (a.wallet || '').toLowerCase()).filter(Boolean);
    const allAgentAddrs = new Set([...agentAddrs, ...registeredAddrs]);
    
    if (!allAgentAddrs.has(fromLower) && !allAgentAddrs.has(toLower)) {
      return res.json({ ok: false, error: '非 Agent 间交易' });
    }
    
    // 名字映射
    const nameMap = {};
    for (const [k, v] of Object.entries(AGENTS)) nameMap[v.addr.toLowerCase()] = v.name;
    for (const a of registered) { if (a.wallet) nameMap[a.wallet.toLowerCase()] = a.name; }
    
    const amount = Number(w3.utils.fromWei(tx.value, 'ether'));
    if (amount <= 0) return res.json({ ok: false, error: '零金额交易' });
    
    // 根据收款方匹配服务
    const services = getServices().filter(s => s.active);
    const matchedService = services.find(s => 
      s.wallet && s.wallet.toLowerCase() === toLower && 
      Math.abs(Number(s.price) - amount) < 0.00001
    ) || services.find(s => s.wallet && s.wallet.toLowerCase() === toLower);
    const reason = matchedService ? matchedService.name : '链上支付';
    
    // 获取区块时间
    const block = await w3.eth.getBlock(tx.blockNumber);
    const blockTime = new Date(Number(block.timestamp) * 1000);
    
    addTx({
      time: blockTime.toLocaleTimeString('zh-CN', {timeZone: 'Asia/Shanghai'}),
      from: nameMap[fromLower] || tx.from.slice(0, 8),
      fromWallet: fromLower,
      to: nameMap[toLower] || (matchedService ? matchedService.expert : '') || (tx.to || '').slice(0, 8),
      amount,
      reason,
      tx: txHash,
      receipt: txHash,
      route_type: 'direct/bsc/BNB',
      verified: '✅ 已验证',
      timestamp: blockTime.toISOString(),
    });
    
    res.json({ ok: true, synced: 1 });
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

// Skill 执行接口 — 买家购买后调用
app.post('/api/skills/execute/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { task, token_address } = req.body || {};
    if (!task) return res.json({ ok: false, error: '缺少 task 参数' });

    // 查找 skill
    const service = services.find(s => s.id === id && s.active);
    if (!service) return res.json({ ok: false, error: '服务不存在或未上架' });

    // 检查 skill 文件
    const skillDir = path.join(__dirname, '..', 'uploaded_skills', id);
    const pyFile = path.join(skillDir, 'skill.py');
    const jsFile = path.join(skillDir, 'skill.js');

    if (fs.existsSync(pyFile)) {
      // Python 执行
      const { execFile } = require('child_process');
      const args = ['-c', `
import json, sys
sys.path.insert(0, '${skillDir}')
from skill import execute
result = execute(${JSON.stringify(task)})
print(json.dumps({"data": result}))
`];
      execFile('python3', args, { timeout: 15000, cwd: skillDir }, (err, stdout, stderr) => {
        if (err) return res.json({ ok: false, error: '执行失败: ' + err.message });
        try {
          const out = JSON.parse(stdout.trim().split('\n').pop());
          res.json({ ok: true, data: out.data });
        } catch(e) {
          res.json({ ok: true, data: stdout.trim() });
        }
      });
    } else if (fs.existsSync(jsFile)) {
      // JS 执行
      const { execFile } = require('child_process');
      const args = ['-e', `
const skill = require('${jsFile}');
const result = skill.execute(${JSON.stringify(task)});
Promise.resolve(result).then(r => { console.log(JSON.stringify({data: r})); process.exit(0); }).catch(e => { console.error(JSON.stringify({error: e.message})); process.exit(1); });
`];
      execFile('node', args, { timeout: 15000 }, (err, stdout, stderr) => {
        if (err) return res.json({ ok: false, error: '执行失败: ' + err.message });
        try {
          const out = JSON.parse(stdout.trim().split('\n').pop());
          res.json({ ok: true, data: out.data });
        } catch(e) {
          res.json({ ok: true, data: stdout.trim() });
        }
      });
    } else {
      res.json({ ok: false, error: 'Skill 文件不存在' });
    }
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

app.listen(PORT, () => {
  console.log(`CryptoMinds Marketplace running on http://localhost:${PORT}`);
});
