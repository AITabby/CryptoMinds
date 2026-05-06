/**
 * 市场路由
 *
 * /api/sellers
 * /api/orders
 * /api/purchases
 * /api/txs
 * /api/balance
 * /api/market
 */

const express = require('express');
const router = express.Router();

function createMarketRoutes({
  getSellers,
  getPurchases,
  getTxs,
  addTx,
  getEscrowAddress,
  getEscrowStats,
  getEscrowOrders,
  w3,
  fetchBnbPrice,
}) {
  // 市场信息
  router.get('/market', async (req, res) => {
    try {
      const sellers = await getSellers();
      const bnbPrice = await fetchBnbPrice();
      const escrowAddr = getEscrowAddress();

      res.json({
        ok: true,
        sellers: sellers.sellers || [],
        bnbPrice,
        escrowAddress: escrowAddr,
        totalSellers: (sellers.sellers || []).length,
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 余额查询
  router.get('/balance', async (req, res) => {
    const wallet = (req.query.wallet || '').trim();
    if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });

    try {
      const balance = await w3.eth.getBalance(wallet);
      res.json({ ok: true, balance: w3.utils.fromWei(balance, 'ether') });
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // 多钱包余额查询
  router.get('/balances', async (req, res) => {
    const wallets = (req.query.wallets || '').split(',').filter(Boolean);
    if (wallets.length === 0) return res.json({ ok: false, error: '缺少 wallets' });

    try {
      const results = {};
      for (const wallet of wallets) {
        try {
          const balance = await w3.eth.getBalance(wallet.trim());
          results[wallet.trim().toLowerCase()] = w3.utils.fromWei(balance, 'ether');
        } catch (e) {
          results[wallet.trim().toLowerCase()] = '0';
        }
      }
      res.json({ ok: true, balances: results });
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // 交易记录（包含 Escrow 订单）
  router.get('/txs', async (req, res) => {
    try {
      const txs = await getTxs();
      if (txs.length > 0) {
        // Add camelCase aliases for frontend compatibility
        return res.json(txs.map(t => ({
          ...t,
          from: t.from_name || t.from_wallet,
          to: t.to_name || t.to_wallet,
          fromWallet: t.from_wallet,
          toWallet: t.to_wallet,
          time: t.timestamp,
        })));
      }
      // tx_logs 为空时，从 escrow_orders 生成交易记录
      if (getEscrowOrders) {
        const orders = await getEscrowOrders();
        const escrowTxs = orders.map(o => ({
          tx: o.on_chain_order_id || o.escrow_id,
          from_wallet: o.buyer_wallet,
          from_name: 'Buyer',
          from: 'Buyer',
          to_wallet: o.seller_wallet,
          to_name: o.seller_agent_id || 'Seller',
          to: o.seller_agent_id || 'Seller',
          amount: parseFloat(o.amount) || 0,
          reason: `Escrow · ${o.state}${o.channel_id === 'bsc-native' ? ' (BSC Testnet)' : ''}`,
          verified: o.state === 'released' ? 1 : 0,
          timestamp: o.created_at ? new Date(o.created_at * 1000).toISOString() : new Date().toISOString(),
          time: o.created_at ? new Date(o.created_at * 1000).toISOString() : new Date().toISOString(),
          _type: 'escrow',
          state: o.state,
          escrow_id: o.escrow_id,
          chain: o.chain,
          channel_id: o.channel_id,
        }));
        return res.json(escrowTxs);
      }
      res.json([]);
    } catch (err) {
      res.json([]);
    }
  });

  // 购买记录
  router.get('/purchases', async (req, res) => {
    try {
      const purchases = await getPurchases();
      res.json(purchases);
    } catch (err) {
      res.json([]);
    }
  });

  // 我的订单
  router.get('/my-orders', async (req, res) => {
    const wallet = (req.query.wallet || '').trim().toLowerCase();
    if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });

    try {
      const purchases = await getPurchases();
      const mine = purchases.filter(p => p.buyer_wallet?.toLowerCase() === wallet);
      res.json({ ok: true, total: mine.length, orders: mine });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 收到的订单
  router.get('/received-orders', async (req, res) => {
    const wallet = (req.query.wallet || '').trim().toLowerCase();
    if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });

    try {
      const purchases = await getPurchases();
      const mine = purchases.filter(p =>
        (p.seller_wallet || p.expert_wallet)?.toLowerCase() === wallet
      );
      res.json({ ok: true, total: mine.length, orders: mine });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 卖家统计
  router.get('/seller-stats', async (req, res) => {
    const wallet = (req.query.wallet || '').trim().toLowerCase();
    if (!wallet) return res.json({ ok: false, error: '缺少 wallet' });

    try {
      const purchases = await getPurchases();
      const mine = purchases.filter(p =>
        (p.seller_wallet || p.expert_wallet)?.toLowerCase() === wallet
      );

      const completed = mine.filter(p => p.status === 'completed' || p.status === 'settled');
      const pending = mine.filter(p => p.status === 'pending');

      const incomeTotal = completed.reduce((sum, p) => sum + (p.price || 0), 0);
      const depositTotal = 0; // 需要从 sellers 表获取

      res.json({
        ok: true,
        income: incomeTotal,
        deposit: depositTotal,
        net: incomeTotal - depositTotal,
        completedOrders: completed.length,
        pendingOrders: pending.length,
        totalOrders: mine.length,
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // Escrow 信息
  router.get('/escrow/info', (req, res) => {
    const addr = getEscrowAddress();
    if (!addr) {
      return res.json({ ok: false, error: 'Escrow 合约未部署' });
    }
    res.json({ ok: true, address: addr });
  });

  // Escrow 统计
  router.get('/escrow/stats', async (req, res) => {
    try {
      const stats = await getEscrowStats();
      res.json({ ok: true, stats });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 实时数据流
  router.get('/live-feed', async (req, res) => {
    try {
      const txs = (await getTxs()).map(t => ({
        ...t,
        _type: 'tx',
        from: t.from_name || t.from_wallet,
        to: t.to_name || t.to_wallet,
        fromWallet: t.from_wallet,
        toWallet: t.to_wallet,
        time: t.timestamp,
      }));
      if (txs.length > 0) {
        return res.json(txs.slice(0, 50));
      }
      // tx_logs 为空时，从 escrow_orders 生成
      if (getEscrowOrders) {
        const orders = await getEscrowOrders(50);
        const escrowTxs = orders.map(o => ({
          tx: o.on_chain_order_id || o.escrow_id,
          from_wallet: o.buyer_wallet,
          from_name: 'Buyer',
          from: 'Buyer',
          to_wallet: o.seller_wallet,
          to_name: o.seller_agent_id || 'Seller',
          to: o.seller_agent_id || 'Seller',
          amount: parseFloat(o.amount) || 0,
          reason: `Escrow · ${o.state}${o.channel_id === 'bsc-native' ? ' (BSC Testnet)' : ''}`,
          verified: o.state === 'released' ? 1 : 0,
          timestamp: o.created_at ? new Date(o.created_at * 1000).toISOString() : new Date().toISOString(),
          time: o.created_at ? new Date(o.created_at * 1000).toISOString() : new Date().toISOString(),
          _type: 'escrow',
          state: o.state,
          escrow_id: o.escrow_id,
          chain: o.chain,
          channel_id: o.channel_id,
        }));
        return res.json(escrowTxs.slice(0, 50));
      }
      res.json([]);
    } catch (err) {
      res.json([]);
    }
  });

  // SSE 实时流
  router.get('/live-stream', (req, res) => {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.write(`data: ${JSON.stringify({ _type: 'connected' })}\n\n`);
    req.on('close', () => {});
  });

  return router;
}

module.exports = { createMarketRoutes };
