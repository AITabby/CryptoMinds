/**
 * 托管客户端
 * 链上资金安全保障，11 态状态机管理
 * @module escrow
 */

const axios = require('axios');

/**
 * 托管状态枚举
 */
const EscrowState = {
  CREATED: 'created',
  FUNDED: 'funded',
  DELIVERED: 'delivered',
  CONFIRMED: 'confirmed',
  DISPUTED: 'disputed',
  ARBITRATING: 'arbitrating',
  RELEASED: 'released',
  REFUNDED: 'refunded',
  SLASHED: 'slashed',
  CANCELLED: 'cancelled',
  EXPIRED: 'expired',
};

class EscrowClient {
  /**
   * @param {string} baseUrl - API 基础 URL
   */
  constructor(baseUrl = 'https://api.cryptominds.ai') {
    this.baseUrl = baseUrl;
    this.client = axios.create({ baseURL: baseUrl });
  }

  /**
   * 创建托管
   * @param {Object} options - 托管选项
   * @param {string} options.buyer - 买家地址
   * @param {string} options.seller - 卖家地址
   * @param {number} options.amount - 托管金额
   * @param {string} [options.token='BNB'] - 代币类型
   * @param {number} [options.timeout=86400] - 超时时间（秒）
   * @param {Object} [options.metadata] - 附加数据
   * @returns {Promise<Object>} 托管信息
   */
  async create({ buyer, seller, amount, token = 'BNB', timeout = 86400, metadata }) {
    const payload = { buyer, seller, amount, token, timeout };
    if (metadata) {
      payload.metadata = metadata;
    }
    const resp = await this.client.post('/api/v1/escrow/create', payload);
    return resp.data;
  }

  /**
   * 查询托管状态
   * @param {string} escrowId - 托管 ID
   * @returns {Promise<Object>} 托管信息
   */
  async get(escrowId) {
    const resp = await this.client.get(`/api/v1/escrow/${escrowId}`);
    return resp.data;
  }

  /**
   * 确认资金已托管（买家调用）
   * @param {string} escrowId - 托管 ID
   * @param {string} txHash - 交易哈希
   * @returns {Promise<Object>} 更新后的托管信息
   */
  async fund(escrowId, txHash) {
    const resp = await this.client.post(`/api/v1/escrow/${escrowId}/fund`, {
      tx_hash: txHash,
    });
    return resp.data;
  }

  /**
   * 提交交付证明（卖家调用）
   * @param {string} escrowId - 托管 ID
   * @param {Object} proof - 交付证明
   * @returns {Promise<Object>} 更新后的托管信息
   */
  async deliver(escrowId, proof) {
    const resp = await this.client.post(`/api/v1/escrow/${escrowId}/deliver`, {
      proof,
    });
    return resp.data;
  }

  /**
   * 确认交付，释放资金（买家调用）
   * @param {string} escrowId - 托管 ID
   * @returns {Promise<Object>} 更新后的托管信息
   */
  async confirm(escrowId) {
    const resp = await this.client.post(`/api/v1/escrow/${escrowId}/release`);
    return resp.data;
  }

  /**
   * 申请退款（买家调用，需满足条件）
   * @param {string} escrowId - 托管 ID
   * @returns {Promise<Object>} 更新后的托管信息
   */
  async refund(escrowId) {
    const resp = await this.client.post(`/api/v1/escrow/${escrowId}/refund`);
    return resp.data;
  }
}

module.exports = { EscrowClient, EscrowState };