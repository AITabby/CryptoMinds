/**
 * PostgreSQL 查询层 — 当 DATABASE_URL 设置时，Express 可以查询 PG 的协议数据
 * 用于 dashboard 展示 escrow/voucher/session_key 状态
 */

const { Pool } = require('pg');

let pool = null;

function getPool() {
  if (!pool && process.env.DATABASE_URL && process.env.DATABASE_URL.startsWith('postgres')) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: 5,
    });
  }
  return pool;
}

function isPgAvailable() {
  return getPool() !== null;
}

async function query(text, params) {
  const p = getPool();
  if (!p) return null;
  const result = await p.query(text, params);
  return result.rows;
}

// ── Protocol data queries ─────────────────────────────────

async function getEscrowOrders(state = null) {
  if (state) {
    return query('SELECT * FROM escrow_orders WHERE state = $1 ORDER BY created_at DESC', [state]);
  }
  return query('SELECT * FROM escrow_orders ORDER BY created_at DESC LIMIT 100');
}

async function getEscrowOrder(escrowId) {
  const rows = await query('SELECT * FROM escrow_orders WHERE escrow_id = $1', [escrowId]);
  return rows ? rows[0] : null;
}

async function getSessionKeys(agentId = null) {
  if (agentId) {
    return query('SELECT * FROM session_keys WHERE agent_id = $1 AND revoked = 0', [agentId]);
  }
  return query('SELECT * FROM session_keys WHERE revoked = 0 ORDER BY created_at DESC LIMIT 50');
}

async function getVouchers(agentId = null) {
  if (agentId) {
    return query('SELECT * FROM vouchers WHERE agent_id = $1', [agentId]);
  }
  return query('SELECT * FROM vouchers ORDER BY created_at DESC LIMIT 50');
}

async function getDisputedEscrows() {
  return query('SELECT * FROM escrow_orders WHERE state = $1', ['disputed']);
}

module.exports = {
  isPgAvailable,
  getEscrowOrders,
  getEscrowOrder,
  getSessionKeys,
  getVouchers,
  getDisputedEscrows,
  query,
};