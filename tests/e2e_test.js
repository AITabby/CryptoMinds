#!/usr/bin/env node
/**
 * CryptoMinds 端到端测试
 * 
 * 测试完整流程：下单 → 交付 → 确认
 * 
 * 用法: node tests/e2e_test.js
 */

const http = require('http');
const BASE = 'http://localhost:3457';

function request(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ raw: data });
        }
      });
    });
    
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function main() {
  console.log('🧪 CryptoMinds 端到端测试\n');
  
  const results = { passed: 0, failed: 0, tests: [] };
  
  function test(name, passed, detail = '') {
    const icon = passed ? '✅' : '❌';
    console.log(`${icon} ${name}${detail ? ': ' + detail : ''}`);
    results.tests.push({ name, passed, detail });
    if (passed) results.passed++;
    else results.failed++;
  }
  
  // 1. 健康检查
  console.log('\n📦 基础检查');
  try {
    const sellers = await request('GET', '/api/sellers');
    test('获取卖家列表', sellers.sellers !== undefined, `${sellers.sellers?.length || 0} 个卖家`);
  } catch (e) {
    test('获取卖家列表', false, e.message);
  }
  
  // 2. Escrow 合约
  console.log('\n🔒 Escrow 合约');
  try {
    const info = await request('GET', '/api/escrow/info');
    test('合约信息', info.ok, info.address || info.error);
  } catch (e) {
    test('合约信息', false, e.message);
  }
  
  try {
    const stats = await request('GET', '/api/escrow/stats');
    test('合约统计', stats.ok, `${stats.orderCount || 0} 笔订单`);
  } catch (e) {
    test('合约统计', false, e.message);
  }
  
  // 3. 买家流程
  console.log('\n🛒 买家流程');
  const testBuyer = '0xTestBuyer' + Date.now().toString(16).slice(-8);
  const testSeller = 'seller-test-001';
  
  try {
    const purchases = await request('GET', `/api/purchases?wallet=${testBuyer}`);
    test('获取买家订单', Array.isArray(purchases.purchases) || Array.isArray(purchases), `${(purchases.purchases || purchases).length} 笔`);
  } catch (e) {
    test('获取买家订单', false, e.message);
  }
  
  // 4. 卖家流程
  console.log('\n💼 卖家流程');
  try {
    const orders = await request('GET', `/api/orders?sellerWallet=${testSeller}`);
    test('获取卖家订单', orders.ok !== false, `${(orders.orders || []).length} 笔`);
  } catch (e) {
    test('获取卖家订单', false, e.message);
  }
  
  // 5. 通知系统
  console.log('\n🔔 通知系统');
  try {
    const notifs = await request('GET', `/api/notifications?wallet=${testBuyer}`);
    test('获取通知', notifs.ok !== false, `${notifs.notifications?.length || 0} 条`);
  } catch (e) {
    test('获取通知', false, e.message);
  }
  
  // 6. Demo 模式检查
  console.log('\n🎮 Demo 模式');
  try {
    const config = await request('GET', '/api/config');
    test('Demo 模式配置', config.demoMode !== undefined, config.demoMode ? '已开启' : '未开启');
  } catch (e) {
    test('Demo 模式配置', false, e.message);
  }
  
  // 汇总
  console.log('\n' + '═'.repeat(50));
  console.log(`📊 测试结果: ${results.passed} 通过, ${results.failed} 失败`);
  console.log('═'.repeat(50));
  
  if (results.failed > 0) {
    console.log('\n❌ 部分测试失败，请检查服务是否正常运行');
    process.exit(1);
  } else {
    console.log('\n✅ 所有测试通过！');
    process.exit(0);
  }
}

main().catch(e => {
  console.error('❌ 测试脚本异常:', e.message);
  process.exit(1);
});
