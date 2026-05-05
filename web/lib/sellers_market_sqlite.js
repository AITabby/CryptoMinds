/**
 * 卖家市场处理（SQLite 版本）
 *
 * 替换 JSON 文件存储，使用 SQLite
 */

const crypto = require('crypto');
const dns = require('dns').promises;
const fs = require('fs');
const net = require('net');
const path = require('path');
const {
  createUnifiedOrder,
  updateOrderStatus,
  checkSellerQuota,
  syncToPurchase,
  ORDER_STATUS
} = require('./order_manager');
const { Database } = require('./database');

// ── 权重计算 ─────────────────────────────────────

function calculateWeight(seller) {
  const rating = seller.rating || 5;
  const totalOrders = seller.totalOrders || 0;
  const deposit = seller.deposit || 0;
  const badRatings = seller.badRatings || 0;

  const ratingScore = Math.max(rating, 1);
  const experienceScore = Math.min(Math.log(totalOrders + 1) * 0.5, 2);
  const depositScore = Math.min(Math.log(deposit / 0.1 + 1) * 0.3, 1.5);
  const badRate = totalOrders > 0 ? badRatings / totalOrders : 0;
  const penalty = badRate > 0.3 ? badRate * 3 : badRate * 1;

  const weight = Math.max(ratingScore + experienceScore + depositScore - penalty, 0.1);
  return Math.round(weight * 100) / 100;
}

// ── SQLite Store ─────────────────────────────────

const { MANAGED_WALLET_ALIASES } = require('./constants');

function createSellersStore(baseDir) {
  // baseDir 是项目根目录，数据库在 web 目录
  const dbPath = path.join(__dirname, '..', 'cryptominds.db');
  let db = null;

  async function getDb() {
    if (!db) {
      db = new Database(dbPath);
      await db.init();
    }
    return db;
  }

  // 同步版本（兼容旧代码）
  function getSellers() {
    // 返回一个 Promise，但旧代码可能期望同步
    // 这里返回一个空结构，实际数据通过异步获取
    return { sellers: [], orders: [], deposits: [] };
  }

  // 同步版已废弃，所有调用方必须用 getSellersAsync
  function getSellers() {
    console.warn('[sellers_market] getSellers() 同步版已废弃，返回空数据。请使用 getSellersAsync()');
    return { sellers: [], orders: [], deposits: [] };
  }

  async function getSellersAsync() {
    const database = await getDb();
    const sellers = await database.getSellers();
    return { sellers: sellers || [], orders: [], deposits: [] };
  }

  async function saveSellersAsync(data) {
    const database = await getDb();
    if (data.sellers) {
      for (const seller of data.sellers) {
        await database.saveSeller(seller);
      }
    }
  }

  function saveSellers(data) {
    // 同步版本：直接写入 JSON（备用）
    console.warn('[sellers_market] saveSellers 同步调用已废弃，请使用 saveSellersAsync');
  }

  return { getDb, getSellers, getSellersAsync, saveSellers, saveSellersAsync, sellersFile: null };
}

// ── Market Handlers ─────────────────────────────

function createSellersMarketHandlers({
  getSellers,
  saveSellers,
  getPurchases,
  savePurchases,
  purchasesFile,
  addTx,
  pythonBin,
  execFileSync,
  w3,
  depositPoolAddress,
  demoMode,
}) {
  const projectRoot = path.join(__dirname, '..', '..');
  const transferBnbScript = path.join(projectRoot, 'transfer_bnb.py');
  const tokenBuyerScript = path.join(projectRoot, 'token_buyer.py');
  const { MANAGED_WALLET_ALIASES } = require('./constants');

  const minDeposit = 0.1;

  function isPrivateIPv4(ip) {
    if (typeof ip !== 'string') return false;
    if (ip.startsWith('0.') || ip.startsWith('10.') || ip.startsWith('127.')) return true;
    if (ip.startsWith('169.254.') || ip.startsWith('192.168.')) return true;
    const parts = ip.split('.').map(p => parseInt(p, 10));
    if (parts.length !== 4 || parts.some(isNaN)) return false;
    return parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31;
  }

  function isPrivateIP(ip) {
    if (!ip) return true;
    if (net.isIPv4(ip)) return isPrivateIPv4(ip);
    if (net.isIPv6(ip)) {
      const n = ip.toLowerCase();
      return n === '::' || n === '::1' || n.startsWith('fc') || n.startsWith('fd') || n.startsWith('fe80:');
    }
    return true;
  }

  async function validateServiceEndpoint(rawEndpoint) {
    const endpoint = typeof rawEndpoint === 'string' ? rawEndpoint.trim() : '';
    if (!endpoint) return { ok: true, endpoint: '' };

    let url;
    try { url = new URL(endpoint); } catch {
      return { ok: false, error: 'Agent API 地址不是合法 URL' };
    }

    if (!['http:', 'https:'].includes(url.protocol)) {
      return { ok: false, error: 'Agent API 地址仅支持 http/https' };
    }

    const hostname = (url.hostname || '').trim().toLowerCase();
    if (!hostname) return { ok: false, error: 'Agent API 地址缺少主机名' };
    if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
      return { ok: false, error: 'Agent API 地址不能指向 localhost' };
    }

    if (net.isIP(hostname)) {
      if (isPrivateIP(hostname)) {
        return { ok: false, error: 'Agent API 地址不能指向内网或本机地址' };
      }
      return { ok: true, endpoint: url.toString().replace(/\/$/, '') };
    }

    try {
      const records = await dns.lookup(hostname, { all: true });
      if (!records.length) return { ok: false, error: 'Agent API 域名解析失败' };
      if (records.some(r => isPrivateIP(r.address))) {
        return { ok: false, error: 'Agent API 地址不能解析到内网或本机地址' };
      }
    } catch {
      return { ok: false, error: 'Agent API 域名解析失败' };
    }

    return { ok: true, endpoint: url.toString().replace(/\/$/, '') };
  }

  async function listSellers(req, res) {
    try {
      const data = await getSellers.getSellersAsync();
      res.json({ ok: true, sellers: data.sellers || [] });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  }

  async function verifyDepositTx(txHash, expectedFrom, expectedAmount) {
    if (demoMode) {
      console.log('[DEMO_MODE] 跳过押金验证:', txHash);
      return { depositAmount: expectedAmount, txHash, demo: true };
    }

    if (!w3) throw new Error('Web3 未初始化');
    if (!txHash || !txHash.startsWith('0x') || txHash.length !== 66) {
      throw new Error('无效的交易哈希格式');
    }

    const tx = await w3.eth.getTransaction(txHash);
    if (!tx) throw new Error('交易未找到，请确认交易已上链');
    const receipt = await w3.eth.getTransactionReceipt(txHash);
    if (!receipt) throw new Error('交易未确认，请稍后重试');
    if (receipt.status !== true && receipt.status !== 1) throw new Error('押金交易执行失败');

    if (tx.from.toLowerCase() !== expectedFrom.toLowerCase()) {
      throw new Error(`交易发送方不一致`);
    }

    if (depositPoolAddress && depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      if (!tx.to || tx.to.toLowerCase() !== depositPoolAddress.toLowerCase()) {
        throw new Error(`押金未发送到正确的押金池地址`);
      }
    }

    const depositAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
    if (depositAmount < expectedAmount) {
      throw new Error(`押金金额不足: 需要 ${expectedAmount} BNB`);
    }

    return { depositAmount, txHash };
  }

  async function verifyPaymentTx(txHash, expectedFrom, expectedTo, expectedAmount) {
    if (demoMode) {
      console.log('[DEMO_MODE] 跳过付款验证:', txHash);
      return { verified: true, demo: true };
    }

    if (!txHash || !/^0x[0-9a-fA-F]{64}$/.test(txHash)) {
      throw new Error('交易哈希格式无效');
    }
    if (!w3) throw new Error('Web3 未初始化');

    const receipt = await w3.eth.getTransactionReceipt(txHash);
    if (!receipt) throw new Error('交易未上链或未确认');
    if (receipt.status !== true && receipt.status !== 1) throw new Error('交易执行失败');

    const tx = await w3.eth.getTransaction(txHash);
    if (!tx) throw new Error('交易未找到');

    if (tx.from.toLowerCase() !== expectedFrom.toLowerCase()) {
      throw new Error(`付款发送方不匹配: 期望 ${expectedFrom}, 实际 ${tx.from}`);
    }
    if (!tx.to || tx.to.toLowerCase() !== expectedTo.toLowerCase()) {
      throw new Error(`付款接收方不匹配: 期望 ${expectedTo}, 实际 ${tx.to || 'null'}`);
    }

    const paidAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
    if (paidAmount < expectedAmount) {
      throw new Error(`付款金额不足: 期望 ${expectedAmount} BNB, 实际 ${paidAmount} BNB`);
    }

    return { verified: true, from: tx.from, to: tx.to, amount: paidAmount };
  }

  async function registerSeller(req, res) {
    const { name, desc, feeRate, wallet, endpoint, depositTx } = req.body;
    if (!name || !wallet) {
      return res.json({ ok: false, error: '缺少必填字段（名称、钱包）' });
    }
    if (!endpoint) {
      return res.json({ ok: false, error: '缺少 Agent API 地址' });
    }

    try {
      const data = await getSellers.getSellersAsync();
      const existing = data.sellers.find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
      if (existing) {
        return res.json({ ok: false, error: '该钱包已入驻' });
      }

      const nameConflict = data.sellers.find(s => s.name.toLowerCase() === name.toLowerCase());
      if (nameConflict) {
        return res.json({ ok: false, error: '该名称已被占用' });
      }

      let normalizedEndpoint = '';
      if (demoMode) {
        try {
          const demoUrl = new URL(endpoint.trim());
          if (!['http:', 'https:'].includes(demoUrl.protocol)) {
            return res.json({ ok: false, error: 'Agent API 地址仅支持 http/https' });
          }
          normalizedEndpoint = demoUrl.toString().replace(/\/$/, '');
        } catch {
          return res.json({ ok: false, error: 'Agent API 地址不是合法 URL' });
        }
      } else {
        const endpointValidation = await validateServiceEndpoint(endpoint);
        if (!endpointValidation.ok) {
          return res.json({ ok: false, error: endpointValidation.error });
        }
        normalizedEndpoint = endpointValidation.endpoint;
      }

      let verifiedDeposit = minDeposit;
      if (depositTx) {
        try {
          const verified = await verifyDepositTx(depositTx, wallet, minDeposit);
          verifiedDeposit = verified.depositAmount;
        } catch (e) {
          return res.json({ ok: false, error: '押金验证失败: ' + e.message });
        }
      } else if (!demoMode) {
        return res.json({ ok: false, error: '请先通过 MetaMask 缴纳押金' });
      }

      if (normalizedEndpoint && !demoMode) {
        try {
          const resp = await fetch(normalizedEndpoint + '/health', {
            method: 'GET',
            signal: AbortSignal.timeout(5000)
          });
          if (!resp.ok) {
            return res.json({ ok: false, error: `Agent API 预检失败: HTTP ${resp.status}` });
          }
        } catch (e) {
          return res.json({ ok: false, error: 'Agent API 预检失败: ' + e.message.slice(0, 100) });
        }
      }

      const seller = {
        wallet: wallet.toLowerCase(),
        name,
        desc: desc || '',
        deposit: verifiedDeposit,
        depositTx: depositTx || null,
        feeRate: feeRate || 0.01,
        strategy: '智能选币',
        rating: 5,
        totalOrders: 0,
        badRatings: 0,
        activeOrders: 0,
        createdAt: new Date().toISOString(),
        endpoint: normalizedEndpoint,
        agentMode: '自主',
        weight: calculateWeight({ rating: 5, totalOrders: 0, deposit: verifiedDeposit, badRatings: 0 }),
      };

      await getSellers.saveSellersAsync({ sellers: [seller] });

      addTx({
        time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
        from: name, fromWallet: wallet.toLowerCase(),
        to: '平台', toWallet: depositPoolAddress || 'platform',
        amount: verifiedDeposit,
        reason: '卖家入驻押金',
        tx: depositTx || 'register',
      });

      return res.json({ ok: true, seller });
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  async function depositSeller(req, res) {
    const { wallet } = req.params;
    let { amount, txHash } = req.body;
    amount = Number(amount);

    if (!Number.isFinite(amount) || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }
    if (!demoMode && !txHash) {
      return res.json({ ok: false, error: '非 Demo 模式必须提供链上押金交易哈希' });
    }

    try {
      const data = await getSellers.getSellersAsync();
      const seller = data.sellers.find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
      if (!seller) {
        return res.json({ ok: false, error: '卖家不存在' });
      }

      if (txHash) {
        try {
          const verified = await verifyDepositTx(txHash, wallet, amount);
          amount = verified.depositAmount;
        } catch (e) {
          return res.json({ ok: false, error: '押金交易验证失败: ' + e.message });
        }
      }

      seller.deposit = (seller.deposit || 0) + amount;
      seller.weight = calculateWeight(seller);
      await getSellers.saveSellersAsync({ sellers: [seller] });

      return res.json({ ok: true, deposit: seller.deposit });
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  async function executeOrder(req, res) {
    const { id } = req.params;
    const { sellerWallet, tokenAddress } = req.body;

    try {
      // 从数据库获取订单和卖家
      const database = await getSellers.getDb();
      const order = await database.getOrder(id);
      if (!order) {
        return res.json({ ok: false, error: '订单不存在' });
      }
      if (order.status !== 'pending' && order.status !== 'paid') {
        return res.json({ ok: false, error: `订单状态不是 pending/paid: ${order.status}` });
      }

      const sellerWalletLower = (sellerWallet || order.seller_wallet)?.toLowerCase();
      const seller = await database.getSeller(sellerWalletLower);
      if (!seller) {
        return res.json({ ok: false, error: '卖家不存在' });
      }

      const buyerAddr = order.buyer_wallet;

      // ── 路径1: 有 endpoint → 调卖家 Agent API ──
      if (seller.endpoint) {
        try {
          await database.updateOrder(id, { status: 'executing', executing_at: new Date().toISOString() });

          console.log(`[executeOrder] 通知卖家Agent执行: ${seller.name} (${seller.endpoint})`);
          const agentUrl = seller.endpoint.replace(/\/\/$/, '') + '/executeOrder';
          const resp = await fetch(agentUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action: 'executeOrder',
              orderId: id,
              sellerName: seller.name,
              strategy: seller.strategy,
              buyerWallet: buyerAddr,
              amount: order.amount,
              currency: 'BNB',
              market: 'bsc-meme',
              venues: ['four.meme', 'pancakeswap'],
            }),
            signal: AbortSignal.timeout(180000),
          });
          const agentResult = await resp.json();

          if (!agentResult.ok) {
            await database.updateOrder(id, { status: 'failed', error: agentResult.error || '卖家Agent执行失败', failed_at: new Date().toISOString() });
            await database.updateSeller(sellerWalletLower, { active_orders: Math.max(0, (seller.activeOrders || 1) - 1) });
            return res.json({ ok: false, error: agentResult.error || '卖家Agent执行失败' });
          }

          const deliveredAt = new Date().toISOString();
          await database.updateOrder(id, {
            status: 'delivered',
            buy_tx: agentResult.swapHash || agentResult.txHash,
            transfer_tx: agentResult.transferHash,
            token_address: agentResult.token || agentResult.tokenAddress,
            token_amount: agentResult.amount || agentResult.tokenAmount,
            token_symbol: agentResult.symbol,
            executed_by: 'seller_agent',
            delivered_at: deliveredAt,
          });
          await database.updateSeller(sellerWalletLower, { active_orders: Math.max(0, (seller.activeOrders || 1) - 1) });

          addTx({
            time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            from: seller.name, fromWallet: seller.wallet,
            to: order.buyer_name || buyerAddr.slice(0, 10), toWallet: buyerAddr,
            amount: order.amount,
            reason: `卖家Agent交付: ${agentResult.symbol || 'Token'}`,
            tx: agentResult.swapHash || agentResult.txHash,
          });

          console.log('[executeOrder] 卖家Agent已交付:', agentResult.swapHash || agentResult.txHash);
          return res.json({
            ok: true, status: 'delivered', executedBy: 'seller_agent',
            buy_tx: agentResult.swapHash || agentResult.txHash,
            transfer_tx: agentResult.transferHash,
            token: agentResult.token || agentResult.tokenAddress,
            tokenAmount: agentResult.amount || agentResult.tokenAmount,
            symbol: agentResult.symbol,
          });
        } catch (e) {
          await database.updateOrder(id, { status: 'failed', error: e.message.slice(0, 200), failed_at: new Date().toISOString() });
          await database.updateSeller(sellerWalletLower, { active_orders: Math.max(0, (seller.activeOrders || 1) - 1) });
          return res.json({ ok: false, error: '卖家Agent调用失败: ' + e.message.slice(0, 200) });
        }
      }

      // ── 路径2: 无 endpoint → 平台代执行（需指定代币地址）──
      const tokenAddr = tokenAddress;
      if (!tokenAddr) {
        return res.json({ ok: false, error: '卖家无 Agent API，需提供 tokenAddress 由平台代执行' });
      }

      const sellerName = MANAGED_WALLET_ALIASES[sellerWalletLower];
      if (!sellerName) {
        return res.json({ ok: false, error: '卖家钱包未在托管列表中，无法执行链上交易' });
      }

      try {
        const output = execFileSync(pythonBin, [
          tokenBuyerScript, sellerName, buyerAddr, tokenAddr, String(order.amount),
        ], { cwd: projectRoot, timeout: 180000, encoding: 'utf-8' });

        const lines = output.trim().split('\n');
        const lastLine = lines[lines.length - 1];
        const result = JSON.parse(lastLine);

        if (!result.ok) {
          return res.json({ ok: false, error: result.error || '买币执行失败', raw: output.slice(-500) });
        }

        await database.updateOrder(id, {
          status: 'completed',
          buy_tx: result.swapHash,
          transfer_tx: result.transferHash,
          token_address: result.token,
          token_amount: result.amount,
          token_symbol: result.symbol,
          completed_at: new Date().toISOString(),
        });
        await database.updateSeller(sellerWalletLower, {
          total_orders: (seller.totalOrders || 0) + 1,
          active_orders: Math.max(0, (seller.activeOrders || 1) - 1),
        });

        addTx({
          time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
          from: seller.name, fromWallet: seller.wallet,
          to: order.buyer_name || buyerAddr.slice(0, 10), toWallet: buyerAddr,
          amount: order.amount,
          reason: `代执行买币: ${result.symbol || 'Token'}`,
          tx: result.swapHash,
        });

        console.log('[executeOrder] 交易完成:', result.swapHash);
        return res.json({
          ok: true, buy_tx: result.swapHash, transfer_tx: result.transferHash,
          token_address: result.token, token_amount: result.amount, token_symbol: result.symbol,
        });
      } catch (e) {
        console.error('[executeOrder] 执行失败:', e.message);
        return res.json({ ok: false, error: '链上执行失败: ' + e.message.slice(0, 200) });
      }
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  async function createOrder(req, res) {
    const { buyerWallet, buyerName, sellerWallet, amount, txHash, paymentMode, serviceId, serviceName, input, escrowOrderId } = req.body;

    if (!buyerWallet || !sellerWallet) {
      return res.json({ ok: false, error: '缺少买家或卖家钱包地址' });
    }
    if (!amount || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }
    if (!txHash && !escrowOrderId) {
      return res.json({ ok: false, error: '缺少交易哈希或托管订单ID' });
    }

    try {
      const database = await getSellers.getDb();
      const data = await getSellers.getSellersAsync();
      const seller = data.sellers.find(s => s.wallet.toLowerCase() === sellerWallet.toLowerCase());
      if (!seller) {
        return res.json({ ok: false, error: '卖家不存在' });
      }

      // 验证链上付款真实性（from/to/amount/确认状态）+ 防重复使用
      if (txHash) {
        if (txHash === 'direct_payment') {
          if (!demoMode) {
            return res.json({ ok: false, error: '生产环境不允许 direct_payment，请提供链上交易哈希或托管订单ID' });
          }
        } else {
          try {
            const existingOrder = await database.getOrderByTxHash(txHash);
            if (existingOrder) {
              return res.json({ ok: false, error: '交易哈希已被使用于其他订单' });
            }

            await verifyPaymentTx(txHash, buyerWallet, sellerWallet, parseFloat(amount));
          } catch (verifyErr) {
            return res.json({ ok: false, error: `付款验证失败: ${verifyErr.message}` });
          }
        }
      }

      const order = createUnifiedOrder({
        buyerWallet,
        buyerName,
        sellerWallet,
        serviceId,
        serviceName: serviceName || seller.name,
        amount,
        txHash,
        paymentMode,
        input,
      });
      order.sellerName = seller.name || '';
      order.feeRate = seller.feeRate || 0;
      if (escrowOrderId) order.escrowOrderId = escrowOrderId;

      seller.activeOrders = (seller.activeOrders || 0) + 1;
      await getSellers.saveSellersAsync({ sellers: [seller] });

      addTx({
        time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
        from: buyerName || buyerWallet.slice(0, 10),
        fromWallet: buyerWallet.toLowerCase(),
        to: seller.name || sellerWallet.slice(0, 10),
        toWallet: sellerWallet.toLowerCase(),
        amount: parseFloat(amount),
        reason: '代执行买币',
        tx: txHash || order.id,
      });

      return res.json({ ok: true, order });
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  async function exitSeller(req, res) {
    const { wallet } = req.body;
    if (!wallet) return res.json({ ok: false, error: '缺少钱包地址' });

    try {
      const data = await getSellers.getSellersAsync();
      const seller = data.sellers.find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
      if (!seller) {
        return res.json({ ok: false, error: '卖家不存在' });
      }
      if (seller.activeOrders > 0) {
        return res.json({ ok: false, error: '有未完成订单，无法退出' });
      }

      const refundAmount = seller.deposit || 0;
      seller.active = false;
      seller.status = 'deregistered';
      seller.exitedAt = new Date().toISOString();
      seller.refundAmount = refundAmount;
      seller.refundStatus = refundAmount > 0 ? 'pending_refund' : 'none';

      await getSellers.saveSellersAsync({ sellers: [seller] });

      return res.json({
        ok: true,
        message: refundAmount > 0 ? `已退出，待退押金 ${refundAmount} BNB` : '已退出',
        refundAmount,
        refundStatus: seller.refundStatus,
      });
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  async function adminRefundSeller(req, res) {
    return res.json({ ok: false, error: 'adminRefundSeller 需要完整实现' });
  }

  async function rateOrder(req, res) {
    const { orderId, rating } = req.body;
    if (!orderId || !rating || rating < 1 || rating > 5) {
      return res.json({ ok: false, error: '参数无效' });
    }

    try {
      const data = await getSellers.getSellersAsync();
      // 这里需要从 orders 表获取订单，简化处理
      return res.json({ ok: true, rating });
    } catch (err) {
      return res.json({ ok: false, error: err.message });
    }
  }

  return {
    listSellers,
    registerSeller,
    depositSeller,
    executeOrder,
    createOrder,
    exitSeller,
    adminRefundSeller,
    rateOrder,
    calculateWeight,
  };
}

module.exports = {
  createSellersStore,
  createSellersMarketHandlers,
};
