/**
 * CryptoMinds SDK - AI Agent 信任基础设施
 *
 * 提供 SACRED 信用分查询、托管创建、争议仲裁等功能。
 *
 * 五维信用分：Stability, Activity, Creditworthiness, Reliability, Ecosystem
 */

const { CreditClient, DIMENSION_NAMES } = require('./credit');
const { EscrowClient, EscrowState } = require('./escrow');
const { ArbitrationClient } = require('./arbitration');

module.exports = {
  CreditClient,
  EscrowClient,
  ArbitrationClient,
  EscrowState,
  DIMENSION_NAMES,
};
