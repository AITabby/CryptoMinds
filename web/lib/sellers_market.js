const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function createSellersStore(baseDir) {
  const sellersFile = path.join(baseDir, 'sellers.json');

  function getSellers() {
    try {
      const data = fs.readFileSync(sellersFile, 'utf8');
      return JSON.parse(data);
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
}) {
  function listSellers(req, res) {
    const data = getSellers();
    res.json({ ok: true, sellers: data.sellers || [] });
  }

  function registerSeller(req, res) {
    const { name, desc, feeRate, wallet, endpoint } = req.body;
    if (!name || !wallet) {
      return res.json({ ok: false, error: '缺少必填字段' });
    }

    const data = getSellers();
    const existing = data.sellers.find((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (existing) {
      return res.json({ ok: false, error: '该钱包已入驻' });
    }

    const seller = {
      wallet,
      name,
      desc: desc || '',
      deposit: 0.1,
      feeRate: feeRate || 0.01,
      strategy: '智能选币',
      rating: 5,
      totalOrders: 0,
      badRatings: 0,
      activeOrders: 0,
      createdAt: new Date().toISOString(),
      endpoint: endpoint || '',
      agentMode: endpoint ? '自主' : '平台托管'
    };

    data.sellers.push(seller);
    saveSellers(data);
    return res.json({ ok: true, seller });
  }

  function depositSeller(req, res) {
    const { wallet } = req.params;
    const { amount, txHash } = req.body;
    if (!amount || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }

    const data = getSellers();
    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (!seller) {
      return res.json({ ok: false, error: '卖家不存在' });
    }

    seller.deposit = (seller.deposit || 0) + amount;
    data.deposits.push({
      wallet: wallet.toLowerCase(),
      amount,
      txHash: txHash || null,
      time: new Date().toISOString()
    });
    saveSellers(data);
    return res.json({ ok: true, deposit: seller.deposit });
  }

  function executeOrder(req, res) {
    const { id } = req.params;
    const { sellerWallet, amount } = req.body;
    const data = getSellers();
    const order = (data.orders || []).find((o) => o.id === id);

    if (!order) return res.json({ ok: false, error: '订单不存在' });
    if (order.status !== 'pending') {
      return res.json({ ok: false, error: `订单状态不是 pending: ${order.status}` });
    }

    const mockBuyTx = `0x${crypto.randomBytes(16).toString('hex')}`;
    const mockTransferTx = `0x${crypto.randomBytes(16).toString('hex')}`;
    const mockTokenAmount = (parseFloat(amount) * (Math.random() * 500 + 100)).toFixed(2);

    order.status = 'completed';
    order.buyTx = mockBuyTx;
    order.transferTx = mockTransferTx;
    order.tokenAddress = `0x${crypto.randomBytes(20).toString('hex')}`;
    order.tokenAmount = mockTokenAmount;
    order.completedAt = new Date().toISOString();

    const seller = data.sellers.find((s) => s.wallet.toLowerCase() === sellerWallet?.toLowerCase());
    if (seller) {
      seller.totalOrders = (seller.totalOrders || 0) + 1;
      seller.activeOrders = Math.max(0, (seller.activeOrders || 1) - 1);
    }

    saveSellers(data);
    return res.json({
      ok: true,
      buy_tx: mockBuyTx,
      transfer_tx: mockTransferTx,
      token_address: order.tokenAddress,
      token_amount: mockTokenAmount
    });
  }

  function createOrder(req, res) {
    const { buyerWallet, buyerName, sellerWallet, amount, txHash, paymentMode } = req.body;
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

    const activeAmount = (data.orders || [])
      .filter((o) => o.sellerWallet?.toLowerCase() === sellerWallet.toLowerCase() && o.status === 'pending')
      .reduce((sum, o) => sum + (parseFloat(o.amount) || 0), 0);
    const quota = (seller.deposit || 0) - activeAmount;
    if (quota < amount) {
      return res.json({ ok: false, error: `卖家可接单额度不足: ${quota.toFixed(4)} BNB < ${amount} BNB` });
    }

    const order = {
      id: `ORD-${Date.now()}`,
      buyerWallet: buyerWallet.toLowerCase(),
      buyerName: buyerName || '',
      sellerWallet: sellerWallet.toLowerCase(),
      sellerName: seller.name || '',
      amount: parseFloat(amount),
      feeRate: seller.feeRate || 0,
      status: 'pending',
      txHash: txHash || null,
      paymentMode: paymentMode || 'direct',
      createdAt: new Date().toISOString()
    };

    data.orders = data.orders || [];
    data.orders.push(order);
    seller.activeOrders = (seller.activeOrders || 0) + 1;
    saveSellers(data);

    try {
      const purchases = getPurchases();
      purchases.push({
        id: order.id,
        serviceId: `${seller.name || ''}-svc`,
        expert: seller.name || '',
        expertWallet: sellerWallet.toLowerCase(),
        serviceName: seller.name || '',
        buyerWallet: buyerWallet.toLowerCase(),
        buyerName: buyerName || '',
        price: parseFloat(amount),
        status: 'pending',
        time: order.createdAt,
        txHash: txHash || null,
        paymentMode: paymentMode || 'direct',
      });
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

  function exitSeller(req, res) {
    const { wallet } = req.body;
    const data = getSellers();
    const idx = data.sellers.findIndex((s) => s.wallet.toLowerCase() === wallet.toLowerCase());
    if (idx === -1) {
      return res.json({ ok: false, error: '卖家不存在' });
    }
    const seller = data.sellers[idx];
    if (seller.activeOrders > 0) {
      return res.json({ ok: false, error: '有未完成订单，无法退出' });
    }
    data.sellers.splice(idx, 1);
    saveSellers(data);
    return res.json({ ok: true });
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
      return res.json({ ok: true, rating });
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
    rateOrder,
  };
}

module.exports = {
  createSellersStore,
  createSellersMarketHandlers,
};
