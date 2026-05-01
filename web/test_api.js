/**
 * CryptoMinds API 集成测试
 */

const assert = require('assert');

const BASE_URL = process.env.TEST_URL || 'http://localhost:3457';

async function test() {
  console.log('=== CryptoMinds API 测试 ===\n');

  // 1. 健康检查
  console.log('[1] 健康检查...');
  const health = await fetch(`${BASE_URL}/healthz`).then(r => r.json());
  assert(health.status === 'ok', '健康检查失败');
  console.log('    ✓ OK\n');

  // 2. 卖家列表
  console.log('[2] 卖家列表...');
  const sellers = await fetch(`${BASE_URL}/api/sellers`).then(r => r.json());
  assert(sellers.ok, '获取卖家失败');
  console.log(`    ✓ ${sellers.sellers.length} 个卖家\n`);

  // 3. 购买记录
  console.log('[3] 购买记录...');
  const purchases = await fetch(`${BASE_URL}/api/purchases`).then(r => r.json());
  console.log(`    ✓ ${purchases.length} 条记录\n`);

  // 4. 市场信息
  console.log('[4] 市场信息...');
  const market = await fetch(`${BASE_URL}/api/market`).then(r => r.json());
  assert(market.ok, '获取市场信息失败');
  console.log(`    ✓ BNB 价格: $${market.bnbPrice}\n`);

  // 5. 配置信息
  console.log('[5] 配置信息...');
  const config = await fetch(`${BASE_URL}/api/config`).then(r => r.json());
  console.log(`    ✓ Demo 模式: ${config.demoMode}\n`);

  // 6. 协议信息（代理到 Python）
  console.log('[6] 协议信息 (Python 代理)...');
  try {
    const protocol = await fetch(`${BASE_URL}/api/protocol/info`).then(r => r.json());
    console.log(`    ✓ 结算通道: ${protocol.channels?.length || 0}`);
    console.log(`    ✓ 验证门: ${protocol.gates?.length || 0}\n`);
  } catch (e) {
    console.log('    ⚠ Python 服务未启动，跳过\n');
  }

  // 7. Escrow 信息
  console.log('[7] Escrow 信息...');
  const escrow = await fetch(`${BASE_URL}/api/escrow/info`).then(r => r.json());
  if (escrow.ok) {
    console.log(`    ✓ 合约地址: ${escrow.address.slice(0, 10)}...\n`);
  } else {
    console.log('    ⚠ 合约未部署\n');
  }

  console.log('=== 测试完成 ===');
}

test().catch(err => {
  console.error('测试失败:', err.message);
  process.exit(1);
});
