/**
 * 数据存储适配器
 *
 * 统一的数据访问层，支持 SQLite（主）和 JSON（备用）
 * 让 server.js 可以渐进式迁移
 */

const fs = require('fs');
const path = require('path');
const { Database } = require('./database');

class DataStore {
  constructor(options = {}) {
    this.dbPath = options.dbPath || path.join(__dirname, '..', 'cryptominds.db');
    this.jsonDir = options.jsonDir || path.join(__dirname, '..');
    this.db = null;
    this.ready = false;
  }

  // ── 初始化 ─────────────────────────────────────

  async init() {
    this.db = new Database(this.dbPath);
    await this.db.init();
    this.ready = true;
    console.log('[DataStore] SQLite 初始化完成');
  }

  // ── Sellers ────────────────────────────────────

  async getSellers() {
    const sellers = await this.db.getSellers();
    return { sellers };
  }

  async getSeller(wallet) {
    return this.db.getSeller(wallet);
  }

  async saveSeller(seller) {
    await this.db.saveSeller(seller);
  }

  async updateSeller(wallet, updates) {
    await this.db.updateSeller(wallet, updates);
  }

  // ── Orders ─────────────────────────────────────

  async getOrders(limit = 100) {
    return this.db.getOrders(limit);
  }

  async getOrder(id) {
    return this.db.getOrder(id);
  }

  async getOrdersBySeller(wallet, limit = 100) {
    return this.db.getOrdersBySeller(wallet, limit);
  }

  async getOrdersByBuyer(wallet, limit = 100) {
    return this.db.getOrdersByBuyer(wallet, limit);
  }

  async saveOrder(order) {
    await this.db.saveOrder(order);
  }

  async updateOrder(id, updates) {
    await this.db.updateOrder(id, updates);
  }

  // ── Purchases ──────────────────────────────────

  async getPurchases(limit = 100) {
    return this.db.getPurchases(limit);
  }

  async getPurchase(id) {
    return this.db.getPurchase(id);
  }

  async getPurchasesByBuyer(wallet, limit = 100) {
    return this.db.getPurchasesByBuyer(wallet, limit);
  }

  async getPurchasesByExpert(wallet, limit = 100) {
    return this.db.getPurchasesByExpert(wallet, limit);
  }

  async getPendingPurchases(limit = 100) {
    return this.db.getPendingPurchases(limit);
  }

  async savePurchase(purchase) {
    await this.db.savePurchase(purchase);
  }

  async updatePurchase(id, updates) {
    await this.db.updatePurchase(id, updates);
  }

  // ── TxLogs ─────────────────────────────────────

  async getTxLogs(limit = 100) {
    return this.db.getTxLogs(limit);
  }

  async saveTxLog(log) {
    await this.db.saveTxLog(log);
  }

  // ── Notifications ──────────────────────────────

  async getNotifications(wallet, limit = 50) {
    return this.db.getNotifications(wallet, limit);
  }

  async getUnreadNotifications(wallet) {
    return this.db.getUnreadNotifications(wallet);
  }

  async saveNotification(notification) {
    await this.db.saveNotification(notification);
  }

  async markNotificationRead(id) {
    await this.db.markNotificationRead(id);
  }

  async markAllNotificationsRead(wallet) {
    await this.db.markAllNotificationsRead(wallet);
  }

  // ── PushSubs ───────────────────────────────────

  async getPushSubs(wallet) {
    if (wallet) {
      return this.db.getPushSubs(wallet);
    }
    return this.db.getAllPushSubs();
  }

  async savePushSub(wallet, subscription) {
    await this.db.savePushSub(wallet, subscription);
  }

  async deletePushSub(endpoint) {
    await this.db.deletePushSub(endpoint);
  }

  // ── Agents ─────────────────────────────────────

  async getAgents() {
    return this.db.getAgents();
  }

  async getAgent(idOrWallet) {
    return this.db.getAgent(idOrWallet);
  }

  async saveAgent(agent) {
    await this.db.saveAgent(agent);
  }

  // ── 事务 ───────────────────────────────────────

  async transaction(fn) {
    return this.db.transaction(fn);
  }

  // ── 关闭 ───────────────────────────────────────

  close() {
    if (this.db) {
      this.db.close();
    }
  }
}

// ── 全局实例 ────────────────────────────────────

let _instance = null;

async function getDataStore() {
  if (!_instance) {
    _instance = new DataStore();
    await _instance.init();
  }
  return _instance;
}

function createDataStore(options) {
  return new DataStore(options);
}

module.exports = { DataStore, getDataStore, createDataStore };