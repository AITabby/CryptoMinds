#!/usr/bin/env node
/**
 * 数据库模块测试
 */

const assert = require('assert');
const path = require('path');
const fs = require('fs');

// 测试数据库路径
const TEST_DB = '/tmp/cryptominds_test.db';

// 清理测试数据库
if (fs.existsSync(TEST_DB)) {
  fs.unlinkSync(TEST_DB);
}

// 设置测试环境
process.chdir(path.join(__dirname, '..', 'web'));

const { Database } = require('../web/lib/database');

async function runTests() {
  console.log('=== 数据库模块测试 ===\n');

  const db = new Database(TEST_DB);

  // 1. 初始化
  console.log('[1] 数据库初始化...');
  await db.init();
  assert(fs.existsSync(TEST_DB), '数据库文件应存在');
  console.log('    ✓ OK\n');

  // 2. Seller CRUD
  console.log('[2] Seller CRUD...');
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
  const savedSeller = await db.getSeller(seller.wallet);
  assert(savedSeller, '应该能获取保存的 seller');
  assert(savedSeller.name === seller.name, '名称应匹配');
  console.log('    ✓ 保存和读取 OK');

  await db.updateSeller(seller.wallet, { rating: 5.0 });
  const updatedSeller = await db.getSeller(seller.wallet);
  assert(updatedSeller.rating === 5.0, '评分应更新');
  console.log('    ✓ 更新 OK\n');

  // 3. Purchase CRUD
  console.log('[3] Purchase CRUD...');
  const purchase = {
    id: 'purchase-test-001',
    buyer_wallet: '0xbuyer1234567890abcdef1234567890abcdef',
    expert_wallet: seller.wallet,
    price: 0.01,
    status: 'pending',
    payment: { mode: 'direct_bnb', hash: '0xabc123' },
  };

  await db.savePurchase(purchase);
  const savedPurchase = await db.getPurchase(purchase.id);
  assert(savedPurchase, '应该能获取保存的 purchase');
  assert(savedPurchase.status === 'pending', '状态应匹配');
  console.log('    ✓ 保存和读取 OK');

  await db.updatePurchase(purchase.id, { status: 'completed' });
  const updatedPurchase = await db.getPurchase(purchase.id);
  assert(updatedPurchase.status === 'completed', '状态应更新');
  console.log('    ✓ 更新 OK\n');

  // 4. TxLog
  console.log('[4] TxLog...');
  const txLog = {
    tx: '0xtxhash1234567890abcdef1234567890abcdef1234567890abcdef12345678',
    from_wallet: seller.wallet,
    to_wallet: '0xbuyer1234567890abcdef1234567890abcdef',
    amount: 0.01,
    reason: 'Test transaction',
  };

  await db.saveTxLog(txLog);
  const txLogs = await db.getTxLogs();
  assert(txLogs.length > 0, '应该有交易日志');
  console.log('    ✓ OK\n');

  // 5. Notification
  console.log('[5] Notification...');
  const notification = {
    id: 'ntf-test-001',
    type: 'new_order',
    target_wallet: seller.wallet,
    order_id: purchase.id,
    service_name: 'Test Service',
  };

  await db.saveNotification(notification);
  const notifications = await db.getNotifications(seller.wallet);
  assert(notifications.length > 0, '应该有通知');
  console.log('    ✓ OK\n');

  // 6. PushSub
  console.log('[6] PushSub...');
  const subscription = {
    endpoint: 'https://fcm.googleapis.com/test',
    keys: { p256dh: 'test_key', auth: 'test_auth' },
  };

  await db.savePushSub(seller.wallet, subscription);
  const pushSubs = await db.getPushSubs(seller.wallet);
  assert(pushSubs.length > 0, '应该有推送订阅');
  console.log('    ✓ OK\n');

  // 7. Agent
  console.log('[7] Agent...');
  const agent = {
    id: 'agent-test-001',
    wallet: seller.wallet,
    name: 'Test Agent',
    skills: ['token_delivery', 'data_delivery'],
    active: true,
  };

  await db.saveAgent(agent);
  const savedAgent = await db.getAgent(agent.id);
  assert(savedAgent, '应该能获取保存的 agent');
  assert(savedAgent.skills.length === 2, '技能数量应匹配');
  console.log('    ✓ OK\n');

  // 8. 事务
  console.log('[8] 事务...');
  await db.transaction(async (txDb) => {
    await txDb.savePurchase({
      id: 'purchase-tx-test',
      buyer_wallet: seller.wallet,
      status: 'pending',
    });
    await txDb.updatePurchase('purchase-tx-test', { status: 'completed' });
  });
  const txPurchase = await db.getPurchase('purchase-tx-test');
  assert(txPurchase && txPurchase.status === 'completed', '事务应正确提交');
  console.log('    ✓ OK\n');

  // 清理
  db.close();
  fs.unlinkSync(TEST_DB);

  console.log('=== 所有测试通过 ===');
}

runTests().catch(err => {
  console.error('测试失败:', err);
  process.exit(1);
});
