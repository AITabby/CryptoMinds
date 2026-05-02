#!/usr/bin/env node
/**
 * 数据库模块测试 (node:test 格式)
 */

const { test, describe, before, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');

const TEST_DB = '/tmp/cryptominds_test_node.db';

describe('Database', () => {
  let db;

  before(() => {
    if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
    process.chdir(path.join(__dirname, '..', 'web'));
  });

  after(() => {
    if (db) db.close();
    if (fs.existsSync(TEST_DB)) fs.unlinkSync(TEST_DB);
  });

  test('init', async () => {
    const { Database } = require('../web/lib/database');
    db = new Database(TEST_DB);
    await db.init();
    assert.ok(fs.existsSync(TEST_DB));
  });

  test('seller CRUD', async () => {
    const seller = {
      wallet: '0x1234567890abcdef1234567890abcdef12345678',
      name: 'Test Seller',
      desc: 'Test Description',
      deposit: 0.1,
      feeRate: 0.03,
      rating: 4.5,
      totalOrders: 10,
      status: 'approved',
    };

    await db.saveSeller(seller);
    const saved = await db.getSeller(seller.wallet);
    assert.ok(saved);
    assert.equal(saved.name, seller.name);

    await db.updateSeller(seller.wallet, { rating: 5.0 });
    const updated = await db.getSeller(seller.wallet);
    assert.equal(updated.rating, 5.0);
  });

  test('purchase CRUD', async () => {
    const purchase = {
      id: 'purchase-test-001',
      buyer_wallet: '0xbuyer1234567890abcdef1234567890abcdef',
      expert_wallet: '0x1234567890abcdef1234567890abcdef12345678',
      price: 0.01,
      status: 'pending',
      payment: { mode: 'direct_bnb', hash: '0xabc123' },
    };

    await db.savePurchase(purchase);
    const saved = await db.getPurchase(purchase.id);
    assert.ok(saved);
    assert.equal(saved.status, 'pending');

    await db.updatePurchase(purchase.id, { status: 'completed' });
    const updated = await db.getPurchase(purchase.id);
    assert.equal(updated.status, 'completed');
  });

  test('txLog', async () => {
    const txLog = {
      tx: '0xtxhash1234567890abcdef1234567890abcdef1234567890abcdef12345678',
      from_wallet: '0x1234567890abcdef1234567890abcdef12345678',
      to_wallet: '0xbuyer1234567890abcdef1234567890abcdef',
      amount: 0.01,
      reason: 'Test transaction',
    };

    await db.saveTxLog(txLog);
    const logs = await db.getTxLogs();
    assert.ok(logs.length > 0);
  });

  test('notification', async () => {
    const notification = {
      id: 'ntf-test-001',
      type: 'new_order',
      target_wallet: '0x1234567890abcdef1234567890abcdef12345678',
      order_id: 'purchase-test-001',
      service_name: 'Test Service',
    };

    await db.saveNotification(notification);
    const notifications = await db.getNotifications(notification.target_wallet);
    assert.ok(notifications.length > 0);
  });

  test('pushSub', async () => {
    const subscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      keys: { p256dh: 'test_key', auth: 'test_auth' },
    };

    await db.savePushSub('0x1234567890abcdef1234567890abcdef12345678', subscription);
    const subs = await db.getPushSubs('0x1234567890abcdef1234567890abcdef12345678');
    assert.ok(subs.length > 0);
  });

  test('agent', async () => {
    const agent = {
      id: 'agent-test-001',
      wallet: '0x1234567890abcdef1234567890abcdef12345678',
      name: 'Test Agent',
      skills: ['token_delivery', 'data_delivery'],
      active: true,
    };

    await db.saveAgent(agent);
    const saved = await db.getAgent(agent.id);
    assert.ok(saved);
    assert.equal(saved.skills.length, 2);
  });

  test('transaction', async () => {
    await db.transaction(async (txDb) => {
      await txDb.savePurchase({
        id: 'purchase-tx-test',
        buyer_wallet: '0x1234567890abcdef1234567890abcdef12345678',
        status: 'pending',
      });
      await txDb.updatePurchase('purchase-tx-test', { status: 'completed' });
    });
    const result = await db.getPurchase('purchase-tx-test');
    assert.ok(result);
    assert.equal(result.status, 'completed');
  });
});