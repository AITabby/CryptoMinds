/**
 * SACRED 信用分客户端
 * 五维信用分评估：Security, Availability, Consistency, Reliability, Economic
 * @module credit
 */

const axios = require('axios');

class CreditClient {
  /**
   * @param {string} baseUrl - API 基础 URL
   */
  constructor(baseUrl = 'https://api.cryptominds.ai') {
    this.baseUrl = baseUrl;
    this.client = axios.create({ baseURL: baseUrl });
  }

  /**
   * 查询 Agent 信用分
   * @param {string} address - Agent 钱包地址
   * @returns {Promise<Object>} 信用分信息
   */
  async getScore(address) {
    const resp = await this.client.get(`/api/v1/credit/${address}`);
    return resp.data;
  }

  /**
   * 查询信用分历史变化
   * @param {string} address - Agent 钱包地址
   * @param {number} limit - 返回数量
   * @returns {Promise<Object>} 历史记录
   */
  async getHistory(address, limit = 10) {
    const resp = await this.client.get(`/api/v1/credit/${address}/history`, {
      params: { limit },
    });
    return resp.data;
  }

  /**
   * 查询信用分排行榜
   * @param {string} [dimension] - 按特定维度排序
   * @param {number} [limit] - 返回数量
   * @returns {Promise<Object>} 排行榜
   */
  async getRanking(dimension = null, limit = 100) {
    const params = { limit };
    if (dimension) {
      params.dimension = dimension;
    }
    const resp = await this.client.get('/api/v1/credit/ranking', { params });
    return resp.data;
  }
}

module.exports = { CreditClient };