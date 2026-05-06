/**
 * 仲裁客户端
 * 信誉加权仲裁，三分支验证
 * @module arbitration
 */

const axios = require('axios');

class ArbitrationClient {
  /**
   * @param {string} baseUrl - API 基础 URL
   */
  constructor(baseUrl = 'https://api.cryptominds.ai') {
    this.baseUrl = baseUrl;
    this.client = axios.create({ baseURL: baseUrl });
  }

  /**
   * 提交争议
   * @param {Object} options - 争议选项
   * @param {string} options.escrowId - 托管 ID
   * @param {string} options.reason - 争议原因
   * @param {Object} [options.evidence] - 证据数据
   * @returns {Promise<Object>} 争议信息
   */
  async submit({ escrowId, reason, evidence }) {
    const payload = { escrow_id: escrowId, reason };
    if (evidence) {
      payload.evidence = evidence;
    }
    const resp = await this.client.post('/api/v1/arbitrate/submit', payload);
    return resp.data;
  }

  /**
   * 查询争议状态
   * @param {string} disputeId - 争议 ID
   * @returns {Promise<Object>} 争议信息
   */
  async get(disputeId) {
    const resp = await this.client.get(`/api/v1/arbitrate/${disputeId}`);
    return resp.data;
  }

  /**
   * 添加证据
   * @param {string} disputeId - 争议 ID
   * @param {Object} evidence - 证据数据
   * @returns {Promise<Object>} 更新后的争议信息
   */
  async addEvidence(disputeId, evidence) {
    const resp = await this.client.post(
      `/api/v1/arbitrate/${disputeId}/evidence`,
      evidence
    );
    return resp.data;
  }

  /**
   * 查询仲裁员列表
   * @param {string} disputeId - 争议 ID
   * @returns {Promise<Object>} 仲裁员列表
   */
  async getArbitrators(disputeId) {
    const resp = await this.client.get(
      `/api/v1/arbitrate/${disputeId}/arbitrators`
    );
    return resp.data;
  }
}

module.exports = { ArbitrationClient };