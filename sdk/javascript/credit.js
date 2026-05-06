/**
 * SACRED 信用分客户端
 * 五维信用分评估：Stability, Activity, Creditworthiness, Reliability, Ecosystem
 * @module credit
 */

const axios = require('axios');

/**
 * 维度名称映射
 */
const DIMENSION_NAMES = {
  S: 'Stability',
  A: 'Activity',
  C: 'Creditworthiness',
  R: 'Reliability',
  E: 'Ecosystem',
};

class CreditClient {
  /**
   * @param {string} baseUrl - API 基础 URL
   */
  constructor(baseUrl = 'http://localhost:3458') {
    this.baseUrl = baseUrl;
    this.client = axios.create({ baseURL: baseUrl });
  }

  /**
   * 查询 Agent 信用分
   * @param {string} address - Agent 钱包地址或 Agent ID
   * @returns {Promise<Object>} 信用分信息
   *
   * 返回格式:
   * {
   *   "agent_id": "0x...",
   *   "wallet": "0x...",
   *   "total_score": 850,
   *   "grade": "AAA",
   *   "is_cold_start": false,
   *   "dimensions": {
   *     "S": {"dimension": "S", "name": "Stability", "score": 180, "max": 200, ...},
   *     "A": {"dimension": "A", "name": "Activity", "score": 170, "max": 200, ...},
   *     "C": {"dimension": "C", "name": "Creditworthiness", "score": 160, "max": 200, ...},
   *     "R": {"dimension": "R", "name": "Reliability", "score": 176, "max": 200, ...},
   *     "E": {"dimension": "E", "name": "Ecosystem", "score": 164, "max": 200, ...}
   *   },
   *   "calculated_at": 1715040000,
   *   "snapshot_hash": "abc123"
   * }
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
   * @param {number} [limit] - 返回数量
   * @returns {Promise<Object>} 排行榜
   */
  async getRanking(limit = 100) {
    const resp = await this.client.get('/api/v1/credit/ranking', { params: { limit } });
    return resp.data;
  }

  /**
   * 触发重新计算信用分
   * @param {string} address - Agent 地址
   * @param {Object} [options] - 可选数据
   * @param {Array} [options.records] - 履约记录列表
   * @param {Object} [options.credit_data] - 信用货币数据
   * @param {Object} [options.agent_info] - Agent 信息
   * @returns {Promise<Object>} 计算后的信用分结果
   */
  async refreshScore(address, { records, credit_data, agent_info } = {}) {
    const resp = await this.client.post(`/api/v1/credit/${address}/refresh`, {
      agent_id: address,
      wallet: address,
      records: records || [],
      credit_data: credit_data || {},
      agent_info: agent_info || {},
    });
    return resp.data;
  }

  /**
   * 格式化信用分结果为可读字符串
   * @param {Object} result - getScore() 返回的结果
   * @returns {string} 格式化后的字符串
   */
  formatScore(result) {
    const lines = [
      `Agent: ${result.agent_id || 'N/A'}`,
      `Score: ${result.total_score || 0} (${result.grade || 'C'})`,
      `Cold Start: ${result.is_cold_start ? 'Yes' : 'No'}`,
      '',
      'Dimensions:',
    ];

    const dims = result.dimensions || {};
    for (const code of ['S', 'A', 'C', 'R', 'E']) {
      const dim = dims[code] || {};
      const name = dim.name || DIMENSION_NAMES[code] || code;
      const score = dim.score || 0;
      const max = dim.max || 200;
      lines.push(`  ${code} - ${name}: ${score}/${max}`);
    }

    return lines.join('\n');
  }
}

module.exports = { CreditClient, DIMENSION_NAMES };
