const test = require('node:test');
const assert = require('node:assert/strict');
const { Web3 } = require('../web/node_modules/web3');
const {
  buildBuyerActionMessage,
  verifyBuyerActionSignature,
} = require('../web/lib/buyer_auth');

const w3 = new Web3();

test('buyer action signature verifies only the expected action, purchase, and wallet', () => {
  const account = w3.eth.accounts.create();
  const purchaseId = 'purchase-123';
  const message = buildBuyerActionMessage('confirm', purchaseId, account.address);
  const signature = account.sign(message).signature;

  assert.equal(verifyBuyerActionSignature({
    action: 'confirm',
    purchaseId,
    buyerWallet: account.address,
    message,
    signature,
  }), true);

  assert.equal(verifyBuyerActionSignature({
    action: 'refund',
    purchaseId,
    buyerWallet: account.address,
    message,
    signature,
  }), false);

  assert.equal(verifyBuyerActionSignature({
    action: 'confirm',
    purchaseId: 'other-purchase',
    buyerWallet: account.address,
    message,
    signature,
  }), false);
});
