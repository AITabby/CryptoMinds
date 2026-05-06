/**
 * 统一订单管理模块
 * P1: 合并 services/buy 和 orders/create 流程
 */

const crypto = require('crypto');

/**
 * 生成唯一订单ID
 */
function generateOrderId() {
  return `ORD-${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
}

/**
 * 订单状态机
 * pending -> paid -> executing -> completed
 *                    -> failed
 */
const ORDER_STATUS = {
  PENDING: 'pending',      // 待支付
  PAID: 'paid',           // 已支付，待执行
  EXECUTING: 'executing', // 执行中
  COMPLETED: 'completed', // 已完成
  FAILED: 'failed',       // 失败
  CANCELLED: 'cancelled', // 已取消
};

/**
 * 创建统一订单
 * @param {Object} params
 * @param {string} params.buyerWallet - 买家钱包
 * @param {string} params.buyerName - 买家名称
 * @param {string} params.sellerWallet - 卖家钱包
 * @param {string} params.serviceId - 服务ID（可选）
 * @param {number} params.amount - 金额
 * @param {string} params.txHash - 支付交易哈希
 * @param {string} params.paymentMode - 支付模式
 * @param {Object} params.input - 输入参数
 */
function createUnifiedOrder({
  buyerWallet,
  buyerName,
  sellerWallet,
  serviceId,
  serviceName,
  amount,
  txHash,
  paymentMode,
  input,
}) {
  const orderId = generateOrderId();
  const now = new Date().toISOString();

  return {
    id: orderId,
    // 买家信息
    buyerWallet: buyerWallet.toLowerCase(),
    buyerName: buyerName || '',
    // 卖家信息
    sellerWallet: sellerWallet.toLowerCase(),
    sellerName: '',
    // 服务信息
    serviceId: serviceId || null,
    serviceName: serviceName || '',
    // 金额
    amount: parseFloat(amount),
    feeRate: 0,
    // 支付
    txHash: txHash || null,
    paymentMode: paymentMode || 'direct',
    paymentVerified: false,
    // 状态
    status: txHash ? ORDER_STATUS.PAID : ORDER_STATUS.PENDING,
    // 执行结果
    buyTx: null,
    transferTx: null,
    tokenAddress: null,
    tokenAmount: null,
    tokenSymbol: null,
    // 输入
    input: input || '',
    // 时间
    createdAt: now,
    paidAt: txHash ? now : null,
    executingAt: null,
    completedAt: null,
    failedAt: null,
    // 评分
    rating: null,
    rated: false,
  };
}

/**
 * 更新订单状态
 */
function updateOrderStatus(order, newStatus, extra = {}) {
  const now = new Date().toISOString();
  order.status = newStatus;

  switch (newStatus) {
    case ORDER_STATUS.PAID:
      order.paidAt = now;
      break;
    case ORDER_STATUS.EXECUTING:
      order.executingAt = now;
      break;
    case ORDER_STATUS.COMPLETED:
      order.completedAt = now;
      break;
    case ORDER_STATUS.FAILED:
      order.failedAt = now;
      break;
  }

  Object.assign(order, extra);
  return order;
}

/**
 * 验证卖家可接单额度
 */
function checkSellerQuota(seller, orders) {
  const activeAmount = (orders || [])
    .filter(o => 
      o.sellerWallet?.toLowerCase() === seller.wallet.toLowerCase() && 
      [ORDER_STATUS.PENDING, ORDER_STATUS.PAID, ORDER_STATUS.EXECUTING].includes(o.status)
    )
    .reduce((sum, o) => sum + (parseFloat(o.amount) || 0), 0);

  const quota = (seller.deposit || 0) - activeAmount;
  return {
    quota,
    activeAmount,
    canAccept: quota > 0,
  };
}

/**
 * 同步订单到 purchases（兼容旧前端）
 */
function syncToPurchase(order, seller) {
  return {
    id: order.id,
    serviceId: order.serviceId || `${seller.name || 'unknown'}-svc`,
    expert: seller.name || order.sellerName || '',
    expertWallet: order.sellerWallet,
    sellerWallet: order.sellerWallet,
    sellerName: seller.name || order.sellerName || '',
    serviceName: order.serviceName || seller.name || '',
    buyerWallet: order.buyerWallet,
    buyerName: order.buyerName,
    price: order.amount,
    status: order.status,
    txHash: order.txHash,
    paymentMode: order.paymentMode,
    input: order.input,
    time: order.createdAt,
    // 执行结果
    buyTx: order.buyTx,
    transferTx: order.transferTx,
    tokenAddress: order.tokenAddress,
    tokenAmount: order.tokenAmount,
    tokenSymbol: order.tokenSymbol,
    // 评分
    rating: order.rating,
    rated: order.rated,
    // 托管合约订单ID
    escrowOrderId: order.escrowOrderId,
  };
}

module.exports = {
  generateOrderId,
  ORDER_STATUS,
  createUnifiedOrder,
  updateOrderStatus,
  checkSellerQuota,
  syncToPurchase,
};
