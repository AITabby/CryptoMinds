/**
 * 订单路由
 *
 * /api/orders
 * /api/orders/:id
 * /api/orders/:id/result
 * /api/orders/:orderId/refund
 * /api/purchases/confirm/:purchaseId
 * /api/purchases/reject/:purchaseId
 * /api/purchases/pending
 */

const express = require('express');
const router = express.Router();
const { verifyBuyerActionSignature, verifySellerActionSignature } = require('../lib/buyer_auth');

function requireBuyerAuth(req, res, next) {
  const { action, purchaseId, buyerWallet, message, signature } = req.body;
  if (!verifyBuyerActionSignature({ action, purchaseId, buyerWallet, message, signature })) {
    return res.json({ ok: false, error: '买家签名验证失败' });
  }
  req.buyerWallet = (buyerWallet || '').trim().toLowerCase();
  next();
}

function requireSellerAuth(req, res, next) {
  const { action, sellerWallet, message, signature } = req.body;
  const orderId = req.params.orderId || req.params.id;
  if (!verifySellerActionSignature({ action, orderId, sellerWallet, message, signature })) {
    return res.json({ ok: false, error: '卖家签名验证失败' });
  }
  req.sellerWallet = (sellerWallet || '').trim().toLowerCase();
  next();
}

function createOrderRoutes({
  getPurchases,
  getPurchase,
  updatePurchase,
  savePurchase,
  getNotifications,
  addNotification,
  sendPushNotification,
  demoMode,
}) {
  // 获取订单列表
  router.get('/orders', async (req, res) => {
    const wallet = (req.query.wallet || '').trim().toLowerCase();
    const status = req.query.status;

    try {
      let purchases = await getPurchases();

      if (wallet) {
        purchases = purchases.filter(p =>
          p.buyer_wallet?.toLowerCase() === wallet ||
          p.seller_wallet?.toLowerCase() === wallet ||
          p.expert_wallet?.toLowerCase() === wallet
        );
      }

      if (status) {
        purchases = purchases.filter(p => p.status === status);
      }

      res.json({ ok: true, orders: purchases.slice(0, 100) });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 获取单个订单
  router.get('/orders/:id', async (req, res) => {
    const { id } = req.params;
    try {
      const purchase = await getPurchase(id);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }
      res.json({ ok: true, order: purchase });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 提交订单结果
  router.post('/orders/:orderId/result', requireSellerAuth, async (req, res) => {
    const { orderId } = req.params;
    const { sellerWallet, txHash, tokenAddress, tokenAmount, tokenSymbol, report } = req.body;

    try {
      const purchase = await getPurchase(orderId);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }
      const expectedSeller = (purchase.seller_wallet || purchase.expert_wallet || '').toLowerCase();
      if (expectedSeller && req.sellerWallet !== expectedSeller) {
        return res.json({ ok: false, error: '只有订单卖家可以提交结果' });
      }

      // 更新订单状态
      await updatePurchase(orderId, {
        status: 'delivered',
        tx_hash: txHash,
        token_address: tokenAddress,
        token_amount: tokenAmount,
        token_symbol: tokenSymbol,
        report,
        delivered_at: new Date().toISOString(),
      });

      // 通知买家
      await addNotification({
        type: 'order_result',
        targetWallet: purchase.buyer_wallet,
        orderId,
        serviceName: purchase.service_name,
        sellerWallet: purchase.seller_wallet || purchase.expert_wallet,
        sellerName: purchase.expert_name || purchase.expert,
      });

      res.json({ ok: true, message: '结果已提交' });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 获取订单结果
  router.get('/orders/:orderId/result', async (req, res) => {
    const { orderId } = req.params;
    try {
      const purchase = await getPurchase(orderId);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }

      res.json({
        ok: true,
        result: {
          txHash: purchase.tx_hash,
          tokenAddress: purchase.token_address,
          tokenAmount: purchase.token_amount,
          tokenSymbol: purchase.token_symbol,
          report: purchase.report,
          status: purchase.status,
        },
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 确认购买
  router.post('/purchases/confirm/:purchaseId', requireBuyerAuth, async (req, res) => {
    const { purchaseId } = req.params;
    const { rating } = req.body;

    try {
      const purchase = await getPurchase(purchaseId);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }

      await updatePurchase(purchaseId, {
        status: 'completed',
        rating: rating || 5,
        confirmed_at: new Date().toISOString(),
      });

      // 通知卖家
      await addNotification({
        type: 'order_confirmed',
        targetWallet: purchase.seller_wallet || purchase.expert_wallet,
        orderId: purchaseId,
        serviceName: purchase.service_name,
        buyerWallet: purchase.buyer_wallet,
        buyerName: purchase.buyer_name,
      });

      res.json({ ok: true, message: '订单已确认' });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 拒绝购买
  router.post('/purchases/reject/:purchaseId', requireBuyerAuth, async (req, res) => {
    const { purchaseId } = req.params;
    const { reason } = req.body;

    try {
      const purchase = await getPurchase(purchaseId);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }

      await updatePurchase(purchaseId, {
        status: 'rejected',
        reject_reason: reason,
        rejected_at: new Date().toISOString(),
      });

      res.json({ ok: true, message: '订单已拒绝' });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 退款
  router.post('/orders/:orderId/refund', requireBuyerAuth, async (req, res) => {
    const { orderId } = req.params;
    const { reason } = req.body;

    try {
      const purchase = await getPurchase(orderId);
      if (!purchase) {
        return res.json({ ok: false, error: '订单不存在' });
      }

      await updatePurchase(orderId, {
        status: 'refunded',
        refund_reason: reason,
        refunded_at: new Date().toISOString(),
      });

      // 通知买家
      await addNotification({
        type: 'order_refunded',
        targetWallet: purchase.buyer_wallet,
        orderId,
        serviceName: purchase.service_name,
      });

      res.json({ ok: true, message: '订单已退款' });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 待处理订单
  router.get('/purchases/pending', async (req, res) => {
    try {
      const purchases = await getPurchases();
      const pending = purchases.filter(p => p.status === 'pending');
      res.json({ ok: true, purchases: pending });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  return router;
}

module.exports = { createOrderRoutes };
