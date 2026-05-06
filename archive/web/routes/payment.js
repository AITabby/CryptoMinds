/**
 * 支付路由
 *
 * /api/pay/x402
 * /api/pay/x402/split
 * /api/smart-route
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const { execFileSync } = require('child_process');
const { verifyBuyerActionSignature } = require('../lib/buyer_auth');

function requireBuyerAuth(req, res, next) {
  const { action, purchaseId, buyerWallet, message, signature } = req.body;
  if (!verifyBuyerActionSignature({ action, purchaseId, buyerWallet, message, signature })) {
    return res.json({ ok: false, error: '买家签名验证失败' });
  }
  next();
}

function createPaymentRoutes({
  PYTHON_BIN,
  SDK_DIR,
  MANAGED_X402_SCRIPT,
  X402_VERIFY_SCRIPT,
  SMART_ROUTER_SCRIPT,
  demoMode,
  w3,
  getWallets,
}) {
  function _resolveWalletName(address) {
    const wallets = getWallets();
    const lowerAddr = (address || '').toLowerCase();
    for (const [name, info] of Object.entries(wallets)) {
      if ((info.address || '').toLowerCase() === lowerAddr) {
        return name;
      }
    }
    return address.slice(0, 10);
  }
  // x402 支付
  router.post('/pay/x402', requireBuyerAuth, async (req, res) => {
    const { fromWallet, toWallet, amount, paymentInfo } = req.body;

    if (!fromWallet || !toWallet || !amount) {
      return res.json({ ok: false, error: '缺少必要参数' });
    }

    if (demoMode) {
      return res.json({
        ok: true,
        txHash: '0x' + '0'.repeat(64),
        demo: true,
        message: 'Demo 模式：支付已模拟',
      });
    }

    try {
      const fromName = _resolveWalletName(fromWallet);
      const toName = _resolveWalletName(toWallet);
      const payload = JSON.stringify({
        from_name: fromName,
        to_name: toName,
        amount_bnb: amount,
        order_id: paymentInfo?.order_id || `order-${Date.now()}`,
        description: paymentInfo?.description || 'CryptoMinds x402 支付',
      });
      const output = execFileSync(PYTHON_BIN, [
        MANAGED_X402_SCRIPT,
        payload,
      ], {
        timeout: 60000,
        encoding: 'utf-8',
      });

      const result = JSON.parse(output.trim().split('\n').pop());
      res.json(result);
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // x402 分拆支付（逐笔发送，因底层脚本不支持 batch split）
  router.post('/pay/x402/split', requireBuyerAuth, async (req, res) => {
    const { fromWallet, recipients, totalAmount } = req.body;

    if (!fromWallet || !recipients || !totalAmount) {
      return res.json({ ok: false, error: '缺少必要参数' });
    }

    if (!Array.isArray(recipients) || recipients.length === 0) {
      return res.json({ ok: false, error: 'recipients 必须是非空数组' });
    }

    // 验证每笔 recipient 结构
    for (const r of recipients) {
      if (!r.toWallet || !r.amount) {
        return res.json({ ok: false, error: '每个 recipient 需要 toWallet 和 amount' });
      }
    }

    // 验证分拆总额
    const splitTotal = recipients.reduce((sum, r) => sum + (r.amount || 0), 0);
    if (Math.abs(splitTotal - totalAmount) > 0.0001) {
      return res.json({ ok: false, error: '分拆金额与总额不符' });
    }

    if (demoMode) {
      return res.json({
        ok: true,
        txHash: '0x' + '0'.repeat(64),
        demo: true,
        splits: recipients,
      });
    }

    try {
      const results = [];
      for (const r of recipients) {
        const fromName = _resolveWalletName(fromWallet);
        const toName = _resolveWalletName(r.toWallet);
        const payload = JSON.stringify({
          from_name: fromName,
          to_name: toName,
          amount_bnb: r.amount,
          order_id: r.orderId || `split-${Date.now()}-${results.length}`,
          description: r.description || `CryptoMinds x402 分拆支付 (${results.length + 1}/${recipients.length})`,
        });
        const output = execFileSync(PYTHON_BIN, [
          MANAGED_X402_SCRIPT,
          payload,
        ], {
          timeout: 60000,
          encoding: 'utf-8',
        });
        const result = JSON.parse(output.trim().split('\n').pop());
        results.push({ ...result, toWallet: r.toWallet, amount: r.amount });
      }
      const allOk = results.every(r => r.ok);
      res.json({
        ok: allOk,
        splits: results,
        totalOk: results.filter(r => r.ok).length,
        totalFail: results.filter(r => !r.ok).length,
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 智能路由
  router.post('/smart-route', async (req, res) => {
    const { fromWallet, toWallet, amount, preferX402 } = req.body;

    if (!fromWallet || !toWallet || !amount) {
      return res.json({ ok: false, error: '缺少必要参数' });
    }

    try {
      const output = execFileSync(PYTHON_BIN, [
        SMART_ROUTER_SCRIPT,
        fromWallet,
        toWallet,
        String(amount),
        preferX402 ? 'true' : 'false',
      ], {
        timeout: 30000,
        encoding: 'utf-8',
      });

      const result = JSON.parse(output.trim().split('\n').pop());
      res.json(result);
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  return router;
}

module.exports = { createPaymentRoutes };
