const { Web3 } = require('web3');

const w3 = new Web3();

function normalizeWallet(wallet) {
  return (wallet || '').toString().trim().toLowerCase();
}

function buildBuyerActionMessage(action, purchaseId, buyerWallet) {
  return [
    'CryptoMinds buyer action',
    `Action: ${action}`,
    `Purchase: ${purchaseId}`,
    `Buyer: ${normalizeWallet(buyerWallet)}`,
  ].join('\n');
}

function buildSellerActionMessage(action, orderId, sellerWallet) {
  return [
    'CryptoMinds seller action',
    `Action: ${action}`,
    `Order: ${orderId}`,
    `Seller: ${normalizeWallet(sellerWallet)}`,
  ].join('\n');
}

function verifyBuyerActionSignature({ action, purchaseId, buyerWallet, message, signature }) {
  const expectedWallet = normalizeWallet(buyerWallet);
  if (!action || !purchaseId || !expectedWallet || !message || !signature) return false;
  const expectedMessage = buildBuyerActionMessage(action, purchaseId, expectedWallet);
  if (message !== expectedMessage) return false;

  try {
    const recovered = w3.eth.accounts.recover(message, signature);
    return normalizeWallet(recovered) === expectedWallet;
  } catch {
    return false;
  }
}

function verifySellerActionSignature({ action, orderId, sellerWallet, message, signature }) {
  const expectedWallet = normalizeWallet(sellerWallet);
  if (!action || !orderId || !expectedWallet || !message || !signature) return false;
  const expectedMessage = buildSellerActionMessage(action, orderId, expectedWallet);
  if (message !== expectedMessage) return false;

  try {
    const recovered = w3.eth.accounts.recover(message, signature);
    return normalizeWallet(recovered) === expectedWallet;
  } catch {
    return false;
  }
}

module.exports = {
  buildBuyerActionMessage,
  buildSellerActionMessage,
  verifyBuyerActionSignature,
  verifySellerActionSignature,
};
