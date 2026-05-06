/**
 * 通知路由
 *
 * /api/notifications
 * /api/notifications/:id/read
 * /api/notifications/read-all
 * /api/push/vapidPublicKey
 * /api/push/subscribe
 */

const express = require('express');
const router = express.Router();

function createNotificationRoutes({
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getPushSubs,
  savePushSub,
  VAPID_PUBLIC_KEY,
}) {
  // VAPID 公钥
  router.get('/push/vapidPublicKey', (req, res) => {
    res.json({ publicKey: VAPID_PUBLIC_KEY });
  });

  // 推送订阅
  router.post('/push/subscribe', async (req, res) => {
    const { wallet, subscription } = req.body;
    if (!wallet || !subscription) {
      return res.json({ ok: false, error: '缺少 wallet 或 subscription' });
    }
    try {
      await savePushSub(wallet.toLowerCase(), subscription);
      res.json({ ok: true });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 获取通知
  router.get('/notifications', async (req, res) => {
    const wallet = (req.query.wallet || '').trim().toLowerCase();
    if (!wallet) {
      return res.json({ ok: false, error: '缺少 wallet 参数' });
    }
    try {
      const notifications = await getNotifications(wallet, 50);
      const unread = req.query.unread === 'true' ? notifications.filter(n => !n.read) : notifications;
      res.json({
        ok: true,
        total: notifications.length,
        unread: notifications.filter(n => !n.read).length,
        notifications: unread
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 标记单条通知已读
  router.post('/notifications/:id/read', async (req, res) => {
    const { id } = req.params;
    try {
      await markNotificationRead(id);
      res.json({ ok: true });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 标记所有通知已读
  router.post('/notifications/read-all', async (req, res) => {
    const wallet = (req.query.wallet || req.body.wallet || '').trim().toLowerCase();
    if (!wallet) {
      return res.json({ ok: false, error: '缺少 wallet' });
    }
    try {
      await markAllNotificationsRead(wallet);
      res.json({ ok: true });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  return router;
}

module.exports = { createNotificationRoutes };
