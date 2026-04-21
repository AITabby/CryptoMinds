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

function createSellersStore(baseDir) {
  const sellersFile = path.join(baseDir, 'sellers.json');

  function getSellers() {
    try {
      const data = fs.readFileSync(sellersFile, 'utf8');
      const parsed = JSON.parse(data);
      // 为每个 seller 加兼容字段，方便旧代码用 service.xxx 方式访问
      parsed.sellers = (parsed.sellers || []).map(s => {
        // 如果没有weight或weight过期，现场计算
        if (!s.weight) s.weight = calculateWeight(s);
        return {
          ...s,
          id: s.id || `seller-${(s.wallet || '').slice(2, 8)}`,
          expert: s.expert || s.name,
          price: s.price ?? (s.feeRate || 0.01),
          active: s.active !== false && s.status !== 'deregistered',
          status: s.status || 'approved',
          sales: s.sales ?? s.totalOrders ?? 0,
          serviceStatus: s.serviceStatus || s.status || 'approved',
          weight: s.weight,
        };
      });
      return parsed;
    } catch {
      return { sellers: [], orders: [], deposits: [] };
    }
  }

  function saveSellers(data) {
    fs.writeFileSync(sellersFile, JSON.stringify(data, null, 2));
  }

  return { getSellers, saveSellers, sellersFile };
}

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
  const minDeposit = 0.1;

  // 管理钱包别名（用于 token_buyer.py 的 seller_name 参数）
  const managedWalletAliases = {
    '0xd2f899ce74320aef9d8f2359183232a554f4c0e1': 'gangdan',
    '0xce0de97496c20dd773d75f560d3e4494cf542d96': 'tiedan',
    '0x40992619077f0e42a1b7713c02b7324fa1d8715c': 'choudan',
    '0x0badb40bed90515cb436282c1d5be059d17566bc': 'pidan',
    '0x4190877f1959e260b4613793e3d07e8a332bc44b': 'ludan',
  };

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
      return { ok: false, error: 'Agent API 地址不是合法 URL' };
    }

    if (!['http:', 'https:'].includes(url.protocol)) {
      return { ok: false, error: 'Agent API 地址仅支持 http/https' };
    }

    const hostname = (url.hostname || '').trim().toLowerCase();
    if (!hostname) {
      return { ok: false, error: 'Agent API 地址缺少主机名' };
    }
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
      if (!records.length) {
        return { ok: false, error: 'Agent API 域名解析失败' };
      }
      if (records.some(record => isPrivateIP(record.address))) {
        return { ok: false, error: 'Agent API 地址不能解析到内网或本机地址' };
      }
    } catch {
      return { ok: false, error: 'Agent API 域名解析失败' };
    }

    return { ok: true, endpoint: url.toString().replace(/\/$/, '') };
  }

  function listSellers(req, res) {
    const data = getSellers();
    res.json({ ok: true, sellers: data.sellers || [] });
  }

  // 链上验证押金交易
  async function verifyDepositTx(txHash, expectedFrom, expectedAmount) {
    // P3: Demo 模式下跳过真实验证
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

    // 验证发送方
    if (tx.from.toLowerCase() !== expectedFrom.toLowerCase()) {
      throw new Error(`交易发送方 (${tx.from.slice(0,10)}...) 与卖家钱包 (${expectedFrom.slice(0,10)}...) 不一致`);
    }

    // 验证接收方（押金池地址）
    if (depositPoolAddress && depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      if (!tx.to || tx.to.toLowerCase() !== depositPoolAddress.toLowerCase()) {
        throw new Error(`押金未发送到正确的押金池地址 (期望: ${depositPoolAddress.slice(0,10)}..., 实际: ${tx.to?.slice(0,10) || 'null'}...)`);
      }
    }

    // 验证金额
    const depositAmount = parseFloat(w3.utils.fromWei(tx.value, 'ether'));
    if (depositAmount < expectedAmount) {
      throw new Error(`押金金额不足: 需要 ${expectedAmount} BNB, 实际 ${depositAmount} BNB`);
    }

    return { depositAmount, txHash };
  }

  // ── 权重计算：评分×完成量×押金系数 / 差评惩罚 ──
  // 权重越高 → 排名越靠前 → 被匹配概率越大
  function calculateWeight(seller) {
    const rating = seller.rating || 5;
    const totalOrders = seller.totalOrders || 0;
    const deposit = seller.deposit || 0;
    const badRatings = seller.badRatings || 0;

    // 基础分 = 评分 (1-5)
    const ratingScore = Math.max(rating, 1);

    // 经验分 = ln(完成订单+1) × 0.5，封顶2分
    const experienceScore = Math.min(Math.log(totalOrders + 1) * 0.5, 2);

    // 押金分 = ln(押金/0.1 + 1) × 0.3，封顶1.5分
    const depositScore = Math.min(Math.log(deposit / 0.1 + 1) * 0.3, 1.5);

    // 差评惩罚 = 差评率 × 3（差评率>30%惩罚严重）
    const badRate = totalOrders > 0 ? badRatings / totalOrders : 0;
    const penalty = badRate > 0.3 ? badRate * 3 : badRate * 1;

    const weight = Math.max(ratingScore + experienceScore + depositScore - penalty, 0.1);
    return Math.round(weight * 100) / 100;
  }

  async function registerSeller(req, res) {
    const { name, desc, feeRate, wallet, endpoint, depositTx } = req.body;
    if (!name || !wallet) {
      return res.json({ ok: false, error: '缺少必填字段（名称、钱包）' });
    }
    // 真实模式下卖家必须有endpoint（自有大脑），Demo模式下可选
    if (!demoMode && !endpoint) {
      return res.json({ ok: false, error: '缺少 Agent API 地址（真实模式下卖家必须有自有大脑）' });
    }

    const data = getSellers();
    const existing = data.sellers.find((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (existing) {
      return res.json({ ok: false, error: '该钱包已入驻' });
    }
    const nameConflict = data.sellers.find((s) => s.name.toLowerCase() === name.toLowerCase());
    if (nameConflict) {
      return res.json({ ok: false, error: '该名称已被占用，请换个名字' });
    }

    const endpointValidation = await validateServiceEndpoint(endpoint);
    if (!endpointValidation.ok) {
      return res.json({ ok: false, error: endpointValidation.error });
    }
    const normalizedEndpoint = endpointValidation.endpoint;

    // 链上验证初始押金（0.1 BNB）— Demo模式下跳过
    let verifiedDeposit = minDeposit;
    if (demoMode && !depositTx) {
      console.log('[DEMO_MODE] 跳过押金验证');
    } else if (depositTx) {
      try {
        const verified = await verifyDepositTx(depositTx, wallet, minDeposit);
        verifiedDeposit = verified.depositAmount;
        console.log(`[registerSeller] 押金验证通过: ${verifiedDeposit} BNB, tx: ${depositTx}`);
      } catch (e) {
        return res.json({ ok: false, error: '押金验证失败: ' + e.message });
      }
    } else if (depositPoolAddress && depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      return res.json({ ok: false, error: '请先通过 MetaMask 缴纳押金，提交交易哈希' });
    }

    // 预检 Agent API 可用性（有endpoint时才检查，Demo模式下跳过）
    if (normalizedEndpoint && !demoMode) {
      try {
        const fetch = (await import('node-fetch')).default;
        const resp = await fetch(normalizedEndpoint + '/health', { method: 'GET', timeout: 5000 });
        if (!resp.ok) {
          return res.json({ ok: false, error: `Agent API 预检失败: HTTP ${resp.status}` });
        }
        console.log(`[registerSeller] Agent API 预检通过: ${normalizedEndpoint}`);
      } catch (e) {
        return res.json({ ok: false, error: 'Agent API 预检失败: ' + e.message.slice(0, 100) });
      }
    } else if (normalizedEndpoint && demoMode) {
      console.log('[DEMO_MODE] 跳过 Agent API 预检:', normalizedEndpoint);
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

    data.sellers.push(seller);
    data.deposits = data.deposits || [];
    data.deposits.push({
      wallet: wallet.toLowerCase(),
      amount: verifiedDeposit,
      txHash: depositTx || null,
      type: 'initial',
      time: new Date().toISOString(),
    });
    saveSellers(data);
    return res.json({ ok: true, seller });
  }

  async function depositSeller(req, res) {
    const { wallet } = req.params;
    let { amount, txHash } = req.body;
    if (!amount || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }

    const data = getSellers();
    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (!seller) {
      return res.json({ ok: false, error: '卖家不存在' });
    }

    // 链上验证补押金交易
    if (txHash) {
      try {
        const verified = await verifyDepositTx(txHash, wallet, amount);
        console.log(`[depositSeller] 补押金验证通过: ${verified.depositAmount} BNB, tx: ${txHash}`);
        // 用链上实际金额
        amount = verified.depositAmount;
      } catch (e) {
        return res.json({ ok: false, error: '押金交易验证失败: ' + e.message });
      }
    } else if (depositPoolAddress && depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      return res.json({ ok: false, error: '请先通过 MetaMask 缴纳押金，提交交易哈希' });
    }

    seller.deposit = (seller.deposit || 0) + amount;
    data.deposits = data.deposits || [];
    data.deposits.push({
      wallet: wallet.toLowerCase(),
      amount,
      txHash: txHash || null,
      type: 'topup',
      time: new Date().toISOString()
    });
    saveSellers(data);
    return res.json({ ok: true, deposit: seller.deposit });
  }

  async function executeOrder(req, res) {
    const { id } = req.params;
    const { sellerWallet, tokenAddress } = req.body;
    const data = getSellers();
    const order = (data.orders || []).find((o) => o.id === id);

    if (!order) return res.json({ ok: false, error: '订单不存在' });
    if (order.status !== 'pending') {
      return res.json({ ok: false, error: `订单状态不是 pending: ${order.status}` });
    }

    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === (sellerWallet || order.sellerWallet)?.toLowerCase());
    if (!seller) return res.json({ ok: false, error: '卖家不存在' });

    const buyerAddr = order.buyerWallet;
    const sellerWalletLower = seller.wallet.toLowerCase();
    const sellerName = managedWalletAliases[sellerWalletLower];

    if (!sellerName) {
      return res.json({ ok: false, error: '卖家钱包未在托管列表中，无法执行链上交易' });
    }

    // 确定要买的代币地址
    let tokenAddr = tokenAddress;
    if (!tokenAddr) {
      // 如果卖家有 endpoint，让卖家 Agent 全权执行（选币+买币+转账）
      if (seller.endpoint) {
        // 更新订单状态为 executing
        order.status = 'executing';
        saveSellers(data);
        
        try {
          console.log(`[executeOrder] 通知卖家Agent执行: ${seller.name} (${seller.endpoint})`);
          const agentUrl = seller.endpoint.replace(/\/$/, '') + '/executeOrder';
          const resp = await fetch(agentUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action: 'executeOrder',
              orderId: order.id,
              sellerName: seller.name,
              strategy: seller.strategy,
              buyerWallet: buyerAddr,
              amount: order.amount,
              currency: 'BNB'
            }),
            signal: AbortSignal.timeout(60000), // Agent执行可能较慢
          });
          const agentResult = await resp.json();

          if (agentResult.ok) {
            // 卖家Agent执行成功，更新订单状态
            updateOrderStatus(order, ORDER_STATUS.COMPLETED, {
              buyTx: agentResult.swapHash || agentResult.txHash,
              transferTx: agentResult.transferHash,
              tokenAddress: agentResult.token || agentResult.tokenAddress,
              tokenAmount: agentResult.amount || agentResult.tokenAmount,
              tokenSymbol: agentResult.symbol,
              executedBy: 'seller_agent',
            });

            seller.totalOrders = (seller.totalOrders || 0) + 1;
            seller.activeOrders = Math.max(0, (seller.activeOrders || 1) - 1);
            saveSellers(data);

            // 同步 purchases
            try {
              const purchases = getPurchases();
              const purchase = purchases.find((p) => p.id === order.id);
              if (purchase) {
                purchase.status = 'completed';
                purchase.txHash = agentResult.swapHash || agentResult.txHash;
                purchase.transferHash = agentResult.transferHash;
                purchase.tokenAmount = agentResult.amount || agentResult.tokenAmount;
                purchase.token = agentResult.token || agentResult.tokenAddress;
                purchase.completedAt = order.completedAt;
                savePurchases(purchases);
              }
            } catch (e) {
              console.error('[executeOrder] 同步 purchase 失败:', e.message);
            }

            addTx({
              time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
              from: seller.name, fromWallet: seller.wallet,
              to: order.buyerName || buyerAddr.slice(0, 10), toWallet: buyerAddr,
              amount: order.amount,
              reason: `卖家Agent执行: ${agentResult.symbol || 'Token'}`,
              tx: agentResult.swapHash || agentResult.txHash,
            });

            console.log('[executeOrder] 卖家Agent执行完成:', agentResult.swapHash || agentResult.txHash);
            return res.json({
              ok: true,
              executedBy: 'seller_agent',
              buy_tx: agentResult.swapHash || agentResult.txHash,
              transfer_tx: agentResult.transferHash,
              token: agentResult.token || agentResult.tokenAddress,
              tokenAmount: agentResult.amount || agentResult.tokenAmount,
              symbol: agentResult.symbol,
            });
          } else {
            // 卖家Agent返回失败，降级到平台代执行
            console.log('[executeOrder] 卖家Agent执行失败，降级平台代执行:', agentResult.error);
          }
        } catch (e) {
          console.log('[executeOrder] 卖家Agent调用失败，降级平台代执行:', e.message);
        }
      }
      // 兜底：默认买一个已知可交易的 meme 代币，避免 Demo 表达退回到稳定币兑换
      if (!tokenAddr) {
        tokenAddr = '0x3518D7aEE5248b9307b8A82B7c3Fa49e073c4444';
        console.log('[executeOrder] Demo模式：使用默认 meme 代币 AIBT');
      }
    }

    console.log(`[executeOrder] 执行买币: seller=${sellerName}, buyer=${buyerAddr}, token=${tokenAddr}, amount=${order.amount} BNB`);

    try {
      // 调用 token_buyer.py 执行真实链上买币 + 转账给买家
      const output = execFileSync(pythonBin, [
        tokenBuyerScript,
        sellerName,
        buyerAddr,
        tokenAddr,
        String(order.amount),
      ], {
        cwd: projectRoot,
        timeout: 180000, // 3分钟超时
        encoding: 'utf-8',
      });

      const lines = output.trim().split('\n');
      const lastLine = lines[lines.length - 1];
      const result = JSON.parse(lastLine);

      if (!result.ok) {
        return res.json({ ok: false, error: result.error || '买币执行失败', raw: output.slice(-500) });
      }

      // 更新订单状态（用统一状态机）
      updateOrderStatus(order, ORDER_STATUS.COMPLETED, {
        buyTx: result.swapHash,
        transferTx: result.transferHash,
        tokenAddress: result.token,
        tokenAmount: result.amount,
        tokenSymbol: result.symbol,
        path: result.path,
      });

      seller.totalOrders = (seller.totalOrders || 0) + 1;
      seller.activeOrders = Math.max(0, (seller.activeOrders || 1) - 1);
      saveSellers(data);

      // 同步更新 purchases
      try {
        const purchases = getPurchases();
        const purchase = purchases.find((p) => p.id === order.id);
        if (purchase) {
          purchase.status = 'completed';
          purchase.txHash = result.swapHash;
          purchase.transferHash = result.transferHash;
          purchase.tokenAmount = result.amount;
          purchase.token = result.token;
          purchase.completedAt = order.completedAt;
          savePurchases(purchases);
        }
      } catch (e) {
        console.error('[executeOrder] 同步 purchase 失败:', e.message);
      }

      // 记录交易
      addTx({
        time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
        from: seller.name,
        fromWallet: seller.wallet,
        to: order.buyerName || buyerAddr.slice(0, 10),
        toWallet: buyerAddr,
        amount: order.amount,
        reason: `代执行买币: ${result.symbol || 'Token'}`,
        tx: result.swapHash,
      });

      console.log('[executeOrder] 交易完成:', result.swapHash);
      return res.json({
        ok: true,
        buy_tx: result.swapHash,
        transfer_tx: result.transferHash,
        token_address: result.token,
        token_amount: result.amount,
        token_symbol: result.symbol,
        path: result.path,
      });
    } catch (e) {
      console.error('[executeOrder] 执行失败:', e.message);
      return res.json({ ok: false, error: '链上执行失败: ' + e.message.slice(0, 200) });
    }
  }

  function createOrder(req, res) {
    const { buyerWallet, buyerName, sellerWallet, amount, txHash, paymentMode, serviceId, serviceName, input, escrowOrderId } = req.body;
    if (!buyerWallet || !sellerWallet) {
      return res.json({ ok: false, error: '缺少买家或卖家钱包地址' });
    }
    if (!amount || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }

    const data = getSellers();
    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === sellerWallet.toLowerCase());
    if (!seller) {
      return res.json({ ok: false, error: '卖家不存在' });
    }

    // 用统一模块检查额度
    const { quota, activeAmount, canAccept } = checkSellerQuota(seller, data.orders);
    if (quota < amount) {
      return res.json({ ok: false, error: `卖家可接单额度不足: ${quota.toFixed(4)} BNB < ${amount} BNB` });
    }

    // 用统一模块创建订单
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

    data.orders = data.orders || [];
    data.orders.push(order);
    seller.activeOrders = (seller.activeOrders || 0) + 1;
    saveSellers(data);

    // 同步到 purchases（兼容旧前端）
    try {
      const purchases = getPurchases();
      purchases.push(syncToPurchase(order, seller));
      savePurchases(purchases);
    } catch (e) {
      console.error('sync purchase error:', e);
    }

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
  }

  async function exitSeller(req, res) {
    const { wallet } = req.body;
    if (!wallet) return res.json({ ok: false, error: '缺少钱包地址' });

    const data = getSellers();
    const idx = data.sellers.findIndex((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (idx === -1) {
      return res.json({ ok: false, error: '卖家不存在' });
    }
    const seller = data.sellers[idx];
    if (seller.activeOrders > 0) {
      return res.json({ ok: false, error: '有未完成订单，无法退出' });
    }

    const refundAmount = seller.deposit || 0;

    // 标记退出，记录退款信息
    seller.active = false;
    seller.status = 'deregistered';
    seller.exitedAt = new Date().toISOString();
    seller.refundAmount = refundAmount;
    seller.refundStatus = refundAmount > 0 ? 'pending_refund' : 'none';

    // 不删除，保留记录
    data.sellers[idx] = seller;

    // 记录退出操作
    data.deposits = data.deposits || [];
    data.deposits.push({
      wallet: wallet.toLowerCase(),
      amount: refundAmount,
      type: 'exit_pending_refund',
      time: new Date().toISOString(),
    });

    saveSellers(data);
    console.log(`[exitSeller] 卖家 ${seller.name} 已退出，待退押金: ${refundAmount} BNB`);

    return res.json({
      ok: true,
      message: refundAmount > 0
        ? `已退出，待退押金 ${refundAmount} BNB（管理员处理中）`
        : '已退出',
      refundAmount,
      refundStatus: seller.refundStatus,
    });
  }

  // 管理员触发链上退款
  async function adminRefundSeller(req, res) {
    const { wallet } = req.params;
    const data = getSellers();
    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === wallet.toLowerCase());

    if (!seller) return res.json({ ok: false, error: '卖家不存在' });
    if (seller.status !== 'deregistered') return res.json({ ok: false, error: '卖家未退出' });
    if (seller.refundStatus === 'completed') return res.json({ ok: false, error: '已退款' });
    if (!seller.refundAmount || seller.refundAmount <= 0) return res.json({ ok: false, error: '无押金可退' });

    // 检查押金池是否在托管钱包中
    const poolAlias = managedWalletAliases[depositPoolAddress?.toLowerCase()];
    if (!poolAlias) {
      return res.json({
        ok: false,
        error: `押金池地址 ${depositPoolAddress} 不在托管钱包中，需手动退款`,
        refundAmount: seller.refundAmount,
        sellerWallet: seller.wallet,
      });
    }

    try {
      // 从押金池转回卖家
      const output = execFileSync(pythonBin, [
        transferBnbScript,
        poolAlias,
        seller.wallet,
        String(seller.refundAmount),
      ], {
        cwd: projectRoot,
        timeout: 60000,
        encoding: 'utf-8',
      });

      const result = JSON.parse(output.trim().split('\n').pop());
      if (!result.ok) {
        return res.json({ ok: false, error: '退款交易失败: ' + (result.error || '未知') });
      }

      // 更新退款状态
      seller.refundStatus = 'completed';
      seller.refundTx = result.txHash;
      seller.refundedAt = new Date().toISOString();
      const sellerIdx = data.sellers.findIndex((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
      data.sellers[sellerIdx] = seller;

      data.deposits = data.deposits || [];
      data.deposits.push({
        wallet: wallet.toLowerCase(),
        amount: seller.refundAmount,
        txHash: result.txHash,
        type: 'refund_completed',
        time: new Date().toISOString(),
      });

      saveSellers(data);
      console.log(`[adminRefund] 退款完成: ${seller.name}, ${seller.refundAmount} BNB, tx: ${result.txHash}`);

      return res.json({
        ok: true,
        txHash: result.txHash,
        amount: seller.refundAmount,
      });
    } catch (e) {
      return res.json({ ok: false, error: '退款执行失败: ' + e.message.slice(0, 200) });
    }
  }

  function rateOrder(req, res) {
    try {
      const { orderId, rating } = req.body;
      if (!orderId || !rating || rating < 1 || rating > 5) {
        return res.json({ ok: false, error: '参数无效' });
      }
      const data = getSellers();
      const order = data.orders.find((o) => o.id === orderId);
      if (!order) {
        return res.json({ ok: false, error: '订单不存在' });
      }
      if (order.rated) {
        return res.json({ ok: false, error: '已评价' });
      }
      order.rated = true;
      order.rating = rating;
      const seller = data.sellers.find((s) => s.wallet.toLowerCase() === order.sellerWallet?.toLowerCase());
      if (seller) {
        const totalRatings = seller.totalOrders || 0;
        const oldAvg = seller.rating || 5;
        seller.rating = Math.round(((oldAvg * totalRatings + rating) / (totalRatings + 1)) * 10) / 10;
        if (rating <= 2) seller.badRatings = (seller.badRatings || 0) + 1;
        // 自动计算权重
        seller.weight = calculateWeight(seller);
      }
      saveSellers(data);
      try {
        const purchases = getPurchases();
        const purchase = purchases.find((x) => x.id === orderId);
        if (purchase) {
          purchase.rated = true;
          purchase.rating = rating;
          savePurchases(purchases);
        }
      } catch {}
      return res.json({ ok: true, rating, weight: seller?.weight });
    } catch (e) {
      return res.json({ ok: false, error: e.message });
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
