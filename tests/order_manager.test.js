const test = require('node:test');
const assert = require('node:assert/strict');
const {
  ORDER_STATUS,
  createUnifiedOrder,
  updateOrderStatus,
  syncToPurchase,
} = require('../web/lib/order_manager');

test('escrow paid orders sync seller fields and can move through delivery lifecycle', () => {
  const order = createUnifiedOrder({
    buyerWallet: '0xD2f899CE74320AEf9D8F2359183232A554F4C0E1',
    buyerName: 'Buyer Agent',
    sellerWallet: '0xce0DE97496c20Dd773d75F560d3e4494cF542d96',
    serviceId: 'momentum-one',
    serviceName: 'Momentum One',
    amount: 0.03,
    txHash: '0x' + 'a'.repeat(64),
    paymentMode: 'escrow_bnb',
    input: '帮我找一个值得关注的新 meme',
  });
  order.sellerName = 'Momentum One';
  order.escrowOrderId = '0x' + 'b'.repeat(64);

  assert.equal(order.status, ORDER_STATUS.PAID);

  updateOrderStatus(order, ORDER_STATUS.EXECUTING);
  assert.equal(order.status, ORDER_STATUS.EXECUTING);
  assert.ok(order.executingAt);

  updateOrderStatus(order, 'delivered', {
    tokenAddress: '0x3518D7aEE5248b9307b8A82B7c3Fa49e073c4444',
    tokenAmount: '123.45',
    deliveredAt: new Date().toISOString(),
  });
  assert.equal(order.status, 'delivered');

  const purchase = syncToPurchase(order, { name: 'Momentum One' });
  assert.equal(purchase.sellerWallet, order.sellerWallet);
  assert.equal(purchase.sellerName, 'Momentum One');
  assert.equal(purchase.escrowOrderId, order.escrowOrderId);
});
