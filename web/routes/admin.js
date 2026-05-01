/**
 * 管理路由
 *
 * /api/config/deposit
 * /api/escrow/deploy
 * /api/sync-chain
 */

const express = require('express');
const router = express.Router();
const { execFileSync } = require('child_process');
const path = require('path');
const crypto = require('crypto');

function createAdminRoutes({
  PYTHON_BIN,
  projectRoot,
  depositPoolAddress,
  demoMode,
  deployEscrow,
  getEscrowAddress,
  getEscrowStats,
  w3,
  getWallets,
  getManagedAgents,
}) {
  // 管理员认证中间件（双模式：共享密钥 or 链上签名）
  function requireAdmin(req, res, next) {
    // Mode 1: Shared secret (server-to-server)
    const adminSecret = process.env.ADMIN_SECRET;
    if (adminSecret) {
      const supplied = req.headers['x-admin-secret'] || req.body.adminSecret;
      if (supplied) {
        const suppliedBuf = Buffer.from(supplied, 'utf8');
        const secretBuf = Buffer.from(adminSecret, 'utf8');
        // timingSafeEqual requires equal-length buffers; pad shorter one
        if (suppliedBuf.length === secretBuf.length &&
            crypto.timingSafeEqual(suppliedBuf, secretBuf)) {
          return next();
        }
      }
    }

    // Mode 2: Wallet address (legacy, less secure)
    const adminWallets = (process.env.ADMIN_WALLETS || '').split(',').filter(Boolean);
    const caller = req.body.caller || req.query.caller || req.headers['x-admin-wallet'];

    if (caller && adminWallets.some(w => w.toLowerCase() === caller.toLowerCase())) {
      return next();
    }

    return res.json({ ok: false, error: '需要管理员权限' });
  }

  // 押金配置
  router.get('/config/deposit', (req, res) => {
    res.json({
      ok: true,
      depositPoolAddress,
      minDeposit: 0.1,
      currency: 'BNB',
      chain: 'bsc',
    });
  });

  // 部署 Escrow 合约
  router.post('/escrow/deploy', requireAdmin, async (req, res) => {
    const deployerKey = process.env.DEPLOYER_PRIVATE_KEY;
    if (!deployerKey) {
      return res.json({ ok: false, error: '未配置 DEPLOYER_PRIVATE_KEY' });
    }

    try {
      const addr = await deployEscrow(deployerKey);
      res.json({ ok: true, address: addr });
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // 同步链上数据
  router.get('/sync-chain', async (req, res) => {
    const force = req.query.force === 'true';

    try {
      const escrowAddr = getEscrowAddress();
      if (!escrowAddr) {
        return res.json({ ok: false, error: 'Escrow 合约未部署' });
      }

      // 获取链上统计
      const stats = await getEscrowStats();

      res.json({
        ok: true,
        synced: true,
        escrowAddress: escrowAddr,
        stats,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 管理员检查
  router.get('/admin-check', (req, res) => {
    const adminWallets = (process.env.ADMIN_WALLETS || '').split(',').filter(Boolean);
    const caller = req.query.wallet;

    res.json({
      ok: true,
      isAdmin: caller && adminWallets.some(w => w.toLowerCase() === caller.toLowerCase()),
    });
  });

  // 托管钱包状态
  router.get('/managed-wallets', (req, res) => {
    const agents = getManagedAgents();
    res.json({ ok: true, wallets: agents });
  });

  // 待审核卖家列表
  router.get('/admin/pending', requireAdmin, async (req, res) => {

    try {
      // 从数据库获取待审核卖家
      const store = req.app.locals.dataStore;
      if (store) {
        const sellers = await store.getSellers();
        const pending = sellers.filter(s => s.status === 'pending');
        res.json({ ok: true, pending });
      } else {
        res.json({ ok: true, pending: [] });
      }
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // 审核通过
  router.post('/admin/approve/:id', requireAdmin, async (req, res) => {

    // 校验 :id 为合法钱包地址格式
    const id = req.params.id;
    if (!/^0x[a-fA-F0-9]{40}$/.test(id)) {
      return res.json({ ok: false, error: '无效的 ID 格式' });
    }

    try {
      const store = req.app.locals.dataStore;
      if (store) {
        await store.updateSeller(id.toLowerCase(), { status: 'active' });
        res.json({ ok: true, message: '审核通过' });
      } else {
        res.json({ ok: false, error: '数据存储不可用' });
      }
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  // 审核拒绝
  router.post('/admin/reject/:id', requireAdmin, async (req, res) => {

    const id = req.params.id;
    if (!/^0x[a-fA-F0-9]{40}$/.test(id)) {
      return res.json({ ok: false, error: '无效的 ID 格式' });
    }

    try {
      const store = req.app.locals.dataStore;
      if (store) {
        await store.updateSeller(id.toLowerCase(), { status: 'rejected' });
        res.json({ ok: true, message: '已拒绝' });
      } else {
        res.json({ ok: false, error: '数据存储不可用' });
      }
    } catch (e) {
      res.json({ ok: false, error: e.message });
    }
  });

  return router;
}

module.exports = { createAdminRoutes };
