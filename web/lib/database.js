/**
 * SQLite 数据层
 *
 * 替换 JSON 文件存储，提供：
 * - 事务支持
 * - 并发安全 (WAL mode + busy_timeout)
 *
 * ⚠️ SQLite 在 supervisord 多进程环境下仅支持单写入者并发。
 * 生产环境请使用 PostgreSQL (DATABASE_URL) 替代。
 */

const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

class Database {
  constructor(dbPath) {
    this.dbPath = dbPath || path.join(__dirname, '..', 'cryptominds.db');
    this.db = null;
  }

  // ── 初始化 ─────────────────────────────────────

  async init() {
    return new Promise((resolve, reject) => {
      this.db = new sqlite3.Database(this.dbPath, (err) => {
        if (err) return reject(err);
        // WAL mode + busy_timeout for cross-process concurrency safety
        this.db.run('PRAGMA journal_mode=WAL');
        this.db.run('PRAGMA busy_timeout=5000');
        this.db.run('PRAGMA foreign_keys=ON');
        this._createTables().then(resolve).catch(reject);
      });
    });
  }

  async _createTables() {
    const tables = [
      // 卖家
      `CREATE TABLE IF NOT EXISTS sellers (
        wallet TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        desc TEXT,
        deposit REAL DEFAULT 0,
        fee_rate REAL DEFAULT 0.03,
        strategy TEXT,
        rating REAL DEFAULT 0,
        total_orders INTEGER DEFAULT 0,
        bad_ratings INTEGER DEFAULT 0,
        active_orders INTEGER DEFAULT 0,
        sales INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        service_status TEXT DEFAULT 'pending',
        endpoint TEXT,
        agent_mode TEXT DEFAULT '自主',
        created_at TEXT,
        updated_at TEXT
      )`,

      // 订单（卖家视角）
      `CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        buyer_wallet TEXT NOT NULL,
        seller_wallet TEXT NOT NULL,
        amount REAL NOT NULL,
        fee REAL,
        total_paid REAL,
        status TEXT DEFAULT 'pending',
        tx_hash TEXT,
        token_address TEXT,
        token_amount TEXT,
        rating INTEGER,
        input TEXT,
        created_at TEXT,
        delivered_at TEXT,
        completed_at TEXT,
        timeout_at TEXT
      )`,

      // 购买记录（买家视角）
      `CREATE TABLE IF NOT EXISTS purchases (
        id TEXT PRIMARY KEY,
        service_id TEXT,
        service_name TEXT,
        buyer_wallet TEXT NOT NULL,
        buyer_name TEXT,
        expert_wallet TEXT,
        expert_name TEXT,
        price REAL,
        status TEXT DEFAULT 'pending',
        payment_mode TEXT,
        payment_hash TEXT,
        payment_verified INTEGER DEFAULT 0,
        payment_from TEXT,
        payment_to TEXT,
        payment_value TEXT,
        payment_block INTEGER,
        payment_demo INTEGER DEFAULT 0,
        tx_hash TEXT,
        input TEXT,
        report TEXT,
        rating INTEGER,
        auto_confirm INTEGER DEFAULT 0,
        auto_confirmed INTEGER DEFAULT 0,
        escrow_order_id TEXT,
        created_at TEXT,
        confirmed_at TEXT
      )`,

      // 交易日志
      `CREATE TABLE IF NOT EXISTS tx_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx TEXT,
        from_wallet TEXT,
        from_name TEXT,
        to_wallet TEXT,
        to_name TEXT,
        amount REAL,
        reason TEXT,
        verified INTEGER DEFAULT 0,
        receipt TEXT,
        timestamp TEXT
      )`,

      // 通知
      `CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        target_wallet TEXT NOT NULL,
        order_id TEXT,
        service_id TEXT,
        service_name TEXT,
        buyer_wallet TEXT,
        buyer_name TEXT,
        seller_wallet TEXT,
        seller_name TEXT,
        input TEXT,
        read INTEGER DEFAULT 0,
        created_at TEXT
      )`,

      // 推送订阅
      `CREATE TABLE IF NOT EXISTS push_subs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wallet TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        p256dh TEXT,
        auth TEXT,
        expiration_time TEXT,
        created_at TEXT
      )`,

      // Agent 注册
      `CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        wallet TEXT NOT NULL UNIQUE,
        name TEXT,
        description TEXT DEFAULT '',
        endpoint TEXT DEFAULT '',
        framework TEXT DEFAULT 'generic',
        skills TEXT,  -- JSON array (capabilities)
        active INTEGER DEFAULT 1,
        online INTEGER DEFAULT 1,
        fee_rate REAL DEFAULT 0,
        deposit REAL DEFAULT 0,
        staked TEXT DEFAULT '0',
        reputation_score REAL DEFAULT 0,
        tasks_completed INTEGER DEFAULT 0,
        tasks_failed INTEGER DEFAULT 0,
        total_volume TEXT DEFAULT '0',
        created_at TEXT
      )`,

      // 履约记录（Python RecordStore 持久化）
      `CREATE TABLE IF NOT EXISTS performance_records (
        record_id TEXT PRIMARY KEY,
        task_id TEXT,
        task_type TEXT,
        buyer_wallet TEXT,
        seller_wallet TEXT,
        seller_agent_id TEXT,
        chain TEXT,
        amount TEXT,
        status TEXT DEFAULT 'pending',
        success INTEGER DEFAULT 0,
        score REAL DEFAULT 0,
        created_at INTEGER,
        completed_at INTEGER,
        response_time_ms INTEGER DEFAULT 0,
        payment_tx TEXT,
        payment_amount TEXT,
        evidence TEXT,
        disputed INTEGER DEFAULT 0,
        dispute_reason TEXT,
        resolution TEXT
      )`,

      // 信用货币（Python CreditRegistry 持久化）
      `CREATE TABLE IF NOT EXISTS credit_currencies (
        currency_id TEXT PRIMARY KEY,
        issuer_agent_id TEXT,
        issuer_wallet TEXT,
        name TEXT,
        symbol TEXT,
        max_supply TEXT,
        backed_by TEXT,
        active INTEGER DEFAULT 1,
        created_at INTEGER,
        accepted_by TEXT
      )`,

      // 信用余额
      `CREATE TABLE IF NOT EXISTS credit_balances (
        currency_id TEXT,
        wallet TEXT,
        balance TEXT,
        PRIMARY KEY (currency_id, wallet)
      )`,
      `CREATE TABLE IF NOT EXISTS escrow_orders (
        escrow_id TEXT PRIMARY KEY,
        task_id TEXT,
        order_id TEXT,
        buyer_wallet TEXT NOT NULL,
        seller_wallet TEXT NOT NULL,
        seller_agent_id TEXT,
        amount TEXT NOT NULL,
        channel_id TEXT,
        chain TEXT DEFAULT 'bsc',
        on_chain_order_id TEXT,
        state TEXT DEFAULT 'created',
        created_at INTEGER,
        funded_at INTEGER,
        delivered_at INTEGER,
        verified_at INTEGER,
        disputed_at INTEGER,
        resolved_at INTEGER,
        seller_timeout_at INTEGER,
        buyer_timeout_at INTEGER,
        dispute_reason TEXT DEFAULT '',
        dispute_initiator TEXT DEFAULT '',
        arbitration_weight_buyer REAL DEFAULT 0,
        arbitration_weight_seller REAL DEFAULT 0,
        resolution TEXT DEFAULT '',
        resolution_reason TEXT DEFAULT '',
        verification_score REAL DEFAULT 0,
        verification_threshold REAL DEFAULT 0.7,
        dispute_window_seconds INTEGER DEFAULT 172800,
        evidence TEXT DEFAULT ''
      )`,
      `CREATE TABLE IF NOT EXISTS session_keys (
        session_key_id TEXT PRIMARY KEY,
        main_wallet TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        available_chains TEXT,
        per_tx_limit TEXT,
        total_quota TEXT,
        total_used TEXT DEFAULT '0',
        callable_actions TEXT,
        created_at INTEGER,
        expires_at INTEGER,
        nonce INTEGER DEFAULT 0,
        revoked INTEGER DEFAULT 0,
        revoked_at INTEGER DEFAULT 0,
        session_address TEXT NOT NULL,
        authorization_signature TEXT NOT NULL
      )`,

      // 索引
      `CREATE INDEX IF NOT EXISTS idx_orders_seller ON orders(seller_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)`,
      `CREATE INDEX IF NOT EXISTS idx_purchases_buyer ON purchases(buyer_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status)`,
      `CREATE INDEX IF NOT EXISTS idx_notifications_wallet ON notifications(target_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read)`,
      `CREATE INDEX IF NOT EXISTS idx_tx_logs_timestamp ON tx_logs(timestamp)`,
      `CREATE INDEX IF NOT EXISTS idx_records_seller ON performance_records(seller_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_records_buyer ON performance_records(buyer_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_records_task ON performance_records(task_id)`,
      `CREATE INDEX IF NOT EXISTS idx_escrow_state ON escrow_orders(state)`,
      `CREATE INDEX IF NOT EXISTS idx_escrow_seller ON escrow_orders(seller_wallet)`,
      `CREATE INDEX IF NOT EXISTS idx_session_keys_agent ON session_keys(agent_id)`,
      `CREATE INDEX IF NOT EXISTS idx_session_keys_wallet ON session_keys(main_wallet)`,
    ];

    for (const sql of tables) {
      await this._run(sql);
    }

    // 迁移: 为旧数据库补充新增列
    await this._migrate();
  }

  async _migrate() {
    const migrations = [
      { table: 'performance_records', column: 'disputed', type: 'INTEGER DEFAULT 0' },
      { table: 'performance_records', column: 'dispute_reason', type: 'TEXT' },
      { table: 'performance_records', column: 'resolution', type: 'TEXT' },
    ];

    for (const m of migrations) {
      try {
        await this._run(`ALTER TABLE ${m.table} ADD COLUMN ${m.column} ${m.type}`);
      } catch (e) {
        // Column already exists — ignore
      }
    }
  }

  // ── 基础操作 ───────────────────────────────────

  _run(sql, params = []) {
    return new Promise((resolve, reject) => {
      this.db.run(sql, params, function(err) {
        if (err) reject(err);
        else resolve({ id: this.lastID, changes: this.changes });
      });
    });
  }

  _get(sql, params = []) {
    return new Promise((resolve, reject) => {
      this.db.get(sql, params, (err, row) => {
        if (err) reject(err);
        else resolve(row);
      });
    });
  }

  _all(sql, params = []) {
    return new Promise((resolve, reject) => {
      this.db.all(sql, params, (err, rows) => {
        if (err) reject(err);
        else resolve(rows);
      });
    });
  }

  // ── 事务 ───────────────────────────────────────

  async transaction(fn) {
    await this._run('BEGIN TRANSACTION');
    try {
      const result = await fn(this);
      await this._run('COMMIT');
      return result;
    } catch (err) {
      await this._run('ROLLBACK');
      throw err;
    }
  }

  // ── Sellers ────────────────────────────────────

  async getSellers() {
    const rows = await this._all('SELECT * FROM sellers');
    return rows.map(row => this._sellerRowToObj(row));
  }

  async getSeller(wallet) {
    const row = await this._get('SELECT * FROM sellers WHERE wallet = ?', [wallet]);
    return row ? this._sellerRowToObj(row) : null;
  }

  async saveSeller(seller) {
    const now = new Date().toISOString();
    const params = [
      seller.wallet,
      seller.name,
      seller.desc || '',
      seller.deposit || 0,
      seller.feeRate || seller.fee_rate || 0.03,
      seller.strategy || '',
      seller.rating || 0,
      seller.totalOrders || seller.total_orders || 0,
      seller.badRatings || seller.bad_ratings || 0,
      seller.activeOrders || seller.active_orders || 0,
      seller.sales || 0,
      seller.status || 'pending',
      seller.serviceStatus || seller.service_status || 'pending',
      seller.endpoint || '',
      seller.agentMode || seller.agent_mode || '自主',
      seller.createdAt || now,
      now,
    ];

    await this._run(`
      INSERT INTO sellers (
        wallet, name, desc, deposit, fee_rate, strategy, rating,
        total_orders, bad_ratings, active_orders, sales, status,
        service_status, endpoint, agent_mode, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(wallet) DO UPDATE SET
        name=excluded.name, desc=excluded.desc, deposit=excluded.deposit,
        fee_rate=excluded.fee_rate, rating=excluded.rating,
        total_orders=excluded.total_orders, bad_ratings=excluded.bad_ratings,
        active_orders=excluded.active_orders, sales=excluded.sales,
        status=excluded.status, service_status=excluded.service_status,
        endpoint=excluded.endpoint, agent_mode=excluded.agent_mode,
        updated_at=excluded.updated_at
    `, params);
  }

  async updateSeller(wallet, updates) {
    const fields = [];
    const params = [];
    for (const [key, value] of Object.entries(updates)) {
      const col = this._camelToSnake(key);
      fields.push(`${col} = ?`);
      params.push(value);
    }
    fields.push('updated_at = ?');
    params.push(new Date().toISOString());
    params.push(wallet);
    await this._run(`UPDATE sellers SET ${fields.join(', ')} WHERE wallet = ?`, params);
  }

  _sellerRowToObj(row) {
    return {
      wallet: row.wallet,
      name: row.name,
      desc: row.desc,
      deposit: row.deposit,
      feeRate: row.fee_rate,
      strategy: row.strategy,
      rating: row.rating,
      totalOrders: row.total_orders,
      badRatings: row.bad_ratings,
      activeOrders: row.active_orders,
      sales: row.sales,
      status: row.status,
      serviceStatus: row.service_status,
      endpoint: row.endpoint,
      agentMode: row.agent_mode,
      createdAt: row.created_at,
      id: `seller-${row.wallet.slice(2, 8)}`,
      active: row.status === 'approved',
      expert: row.name,
      price: row.fee_rate,
      weight: this._calculateWeight(row),
    };
  }

  _calculateWeight(row) {
    const ratingWeight = (row.rating || 0) * 0.4;
    const depositWeight = Math.log10((row.deposit || 0) + 1) * 0.3;
    const salesWeight = Math.log10((row.sales || 0) + 1) * 0.2;
    const feeWeight = (1 - (row.fee_rate || 0.03)) * 0.1;
    return ratingWeight + depositWeight + salesWeight + feeWeight;
  }

  // ── Orders ─────────────────────────────────────

  async getOrders(limit = 100) {
    return this._all('SELECT * FROM orders ORDER BY created_at DESC LIMIT ?', [limit]);
  }

  async getOrder(id) {
    return this._get('SELECT * FROM orders WHERE id = ?', [id]);
  }

  async getOrderByTxHash(txHash) {
    return this._get('SELECT * FROM orders WHERE tx_hash = ?', [txHash]);
  }

  async getOrdersBySeller(wallet, limit = 100) {
    return this._all('SELECT * FROM orders WHERE seller_wallet = ? ORDER BY created_at DESC LIMIT ?', [wallet, limit]);
  }

  async getOrdersByBuyer(wallet, limit = 100) {
    return this._all('SELECT * FROM orders WHERE buyer_wallet = ? ORDER BY created_at DESC LIMIT ?', [wallet, limit]);
  }

  async saveOrder(order) {
    const now = new Date().toISOString();
    const params = [
      order.id,
      order.buyerWallet || order.buyer_wallet,
      order.sellerWallet || order.seller_wallet,
      order.amount,
      order.fee || null,
      order.totalPaid || order.total_paid || null,
      order.status || 'pending',
      order.txHash || order.tx_hash || null,
      order.tokenAddress || order.token_address || null,
      order.tokenAmount || order.token_amount || null,
      order.rating || null,
      order.input || null,
      order.createdAt || order.created_at || now,
      order.deliveredAt || order.delivered_at || null,
      order.completedAt || order.completed_at || null,
      order.timeoutAt || order.timeout_at || null,
    ];

    await this._run(`
      INSERT INTO orders (
        id, buyer_wallet, seller_wallet, amount, fee, total_paid,
        status, tx_hash, token_address, token_amount, rating, input,
        created_at, delivered_at, completed_at, timeout_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        status=excluded.status, tx_hash=excluded.tx_hash,
        token_address=excluded.token_address, token_amount=excluded.token_amount,
        rating=excluded.rating, delivered_at=excluded.delivered_at,
        completed_at=excluded.completed_at
    `, params);
  }

  async updateOrder(id, updates) {
    const fields = [];
    const params = [];
    for (const [key, value] of Object.entries(updates)) {
      const col = this._camelToSnake(key);
      fields.push(`${col} = ?`);
      params.push(value);
    }
    params.push(id);
    await this._run(`UPDATE orders SET ${fields.join(', ')} WHERE id = ?`, params);
  }

  // ── Purchases ──────────────────────────────────

  async getPurchases(limit = 100) {
    return this._all('SELECT * FROM purchases ORDER BY created_at DESC LIMIT ?', [limit]);
  }

  async getPurchase(id) {
    return this._get('SELECT * FROM purchases WHERE id = ?', [id]);
  }

  async getPurchasesByBuyer(wallet, limit = 100) {
    return this._all('SELECT * FROM purchases WHERE buyer_wallet = ? ORDER BY created_at DESC LIMIT ?', [wallet, limit]);
  }

  async getPurchasesByExpert(wallet, limit = 100) {
    return this._all('SELECT * FROM purchases WHERE expert_wallet = ? ORDER BY created_at DESC LIMIT ?', [wallet, limit]);
  }

  async getPendingPurchases(limit = 100) {
    return this._all('SELECT * FROM purchases WHERE status = ? ORDER BY created_at DESC LIMIT ?', ['pending', limit]);
  }

  async savePurchase(purchase) {
    const now = new Date().toISOString();
    const payment = purchase.payment || {};
    const params = [
      purchase.id,
      purchase.serviceId || purchase.service_id || null,
      purchase.serviceName || purchase.service_name || null,
      purchase.buyerWallet || purchase.buyer_wallet,
      purchase.buyerName || purchase.buyer_name || null,
      purchase.expertWallet || purchase.expert_wallet || null,
      purchase.expertName || purchase.expert_name || null,
      purchase.price,
      purchase.status || 'pending',
      payment.mode || null,
      payment.hash || null,
      payment.verified ? 1 : 0,
      payment.from || null,
      payment.to || null,
      payment.value || null,
      payment.blockNumber || payment.block || null,
      payment.demo ? 1 : 0,
      purchase.txHash || purchase.tx_hash || null,
      purchase.input || null,
      purchase.report || null,
      purchase.rating || null,
      purchase.autoConfirm || purchase.auto_confirm ? 1 : 0,
      purchase.autoConfirmed || purchase.auto_confirmed ? 1 : 0,
      purchase.escrowOrderId || purchase.escrow_order_id || null,
      purchase.createdAt || purchase.created_at || purchase.time || now,
      purchase.confirmedAt || purchase.confirmed_at || null,
    ];

    await this._run(`
      INSERT INTO purchases (
        id, service_id, service_name, buyer_wallet, buyer_name,
        expert_wallet, expert_name, price, status, payment_mode,
        payment_hash, payment_verified, payment_from, payment_to,
        payment_value, payment_block, payment_demo, tx_hash, input,
        report, rating, auto_confirm, auto_confirmed, escrow_order_id,
        created_at, confirmed_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        status=excluded.status, report=excluded.report, rating=excluded.rating,
        tx_hash=excluded.tx_hash, confirmed_at=excluded.confirmed_at,
        auto_confirmed=excluded.auto_confirmed
    `, params);
  }

  async updatePurchase(id, updates) {
    const fields = [];
    const params = [];
    for (const [key, value] of Object.entries(updates)) {
      const col = this._camelToSnake(key);
      fields.push(`${col} = ?`);
      params.push(value);
    }
    params.push(id);
    await this._run(`UPDATE purchases SET ${fields.join(', ')} WHERE id = ?`, params);
  }

  // ── TxLogs ─────────────────────────────────────

  async getTxLogs(limit = 100) {
    return this._all('SELECT * FROM tx_logs ORDER BY timestamp DESC LIMIT ?', [limit]);
  }

  async saveTxLog(log) {
    const params = [
      log.tx || null,
      log.fromWallet || log.from_wallet || null,
      log.fromName || log.from || null,
      log.toWallet || log.to_wallet || null,
      log.toName || log.to || null,
      log.amount,
      log.reason || null,
      log.verified ? 1 : 0,
      log.receipt || null,
      log.timestamp || new Date().toISOString(),
    ];
    return this._run(`
      INSERT INTO tx_logs (tx, from_wallet, from_name, to_wallet, to_name, amount, reason, verified, receipt, timestamp)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `, params);
  }

  // ── Notifications ──────────────────────────────

  async getNotifications(wallet, limit = 50) {
    return this._all('SELECT * FROM notifications WHERE target_wallet = ? ORDER BY created_at DESC LIMIT ?', [wallet, limit]);
  }

  async getUnreadNotifications(wallet) {
    return this._all('SELECT * FROM notifications WHERE target_wallet = ? AND read = 0 ORDER BY created_at DESC', [wallet]);
  }

  async saveNotification(notification) {
    const params = [
      notification.id,
      notification.type,
      notification.targetWallet || notification.target_wallet,
      notification.orderId || notification.order_id || null,
      notification.serviceId || notification.service_id || null,
      notification.serviceName || notification.service_name || null,
      notification.buyerWallet || notification.buyer_wallet || null,
      notification.buyerName || notification.buyer_name || null,
      notification.sellerWallet || notification.seller_wallet || null,
      notification.sellerName || notification.seller_name || null,
      notification.input || null,
      notification.read ? 1 : 0,
      notification.createdAt || notification.created_at || new Date().toISOString(),
    ];
    await this._run(`
      INSERT INTO notifications (
        id, type, target_wallet, order_id, service_id, service_name,
        buyer_wallet, buyer_name, seller_wallet, seller_name, input, read, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `, params);
  }

  async markNotificationRead(id) {
    await this._run('UPDATE notifications SET read = 1 WHERE id = ?', [id]);
  }

  async markAllNotificationsRead(wallet) {
    await this._run('UPDATE notifications SET read = 1 WHERE target_wallet = ?', [wallet]);
  }

  // ── PushSubs ───────────────────────────────────

  async getPushSubs(wallet) {
    return this._all('SELECT * FROM push_subs WHERE wallet = ?', [wallet]);
  }

  async getAllPushSubs() {
    return this._all('SELECT * FROM push_subs');
  }

  async savePushSub(wallet, subscription) {
    const params = [
      wallet,
      subscription.endpoint,
      subscription.keys?.p256dh || null,
      subscription.keys?.auth || null,
      subscription.expirationTime || null,
      new Date().toISOString(),
    ];
    await this._run(`
      INSERT INTO push_subs (wallet, endpoint, p256dh, auth, expiration_time, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `, params);
  }

  async deletePushSub(endpoint) {
    await this._run('DELETE FROM push_subs WHERE endpoint = ?', [endpoint]);
  }

  // ── Agents ─────────────────────────────────────

  async getAgents() {
    return this._all('SELECT * FROM agents WHERE active = 1');
  }

  async getAgent(idOrWallet) {
    const row = await this._get('SELECT * FROM agents WHERE id = ? OR wallet = ?', [idOrWallet, idOrWallet]);
    if (!row) return null;
    return {
      ...row,
      skills: row.skills ? JSON.parse(row.skills) : [],
    };
  }

  async saveAgent(agent) {
    const params = [
      agent.id,
      agent.wallet,
      agent.name || '',
      agent.framework || 'generic',
      JSON.stringify(agent.skills || []),
      agent.active ? 1 : 0,
      agent.feeRate || agent.fee_rate || 0,
      agent.deposit || 0,
      agent.createdAt || agent.registeredAt || agent.created_at || new Date().toISOString(),
    ];
    await this._run(`
      INSERT INTO agents (id, wallet, name, framework, skills, active, fee_rate, deposit, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(wallet) DO UPDATE SET
        name=excluded.name, framework=excluded.framework,
        skills=excluded.skills, active=excluded.active
    `, params);
  }

  // ── 工具 ───────────────────────────────────────

  _camelToSnake(str) {
    return str.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
  }

  // ── 迁移 ───────────────────────────────────────

  async migrateFromJson(dataDir) {
    console.log('[db] 开始从 JSON 迁移数据...');

    // Sellers
    const sellersFile = path.join(dataDir, 'sellers.json');
    if (fs.existsSync(sellersFile)) {
      const data = JSON.parse(fs.readFileSync(sellersFile, 'utf8'));
      if (data.sellers) {
        for (const seller of data.sellers) {
          await this.saveSeller(seller);
        }
        console.log(`[db] 迁移 ${data.sellers.length} 个卖家`);
      }
      // Orders in sellers.json
      if (data.orders) {
        for (const order of data.orders) {
          await this.saveOrder(order);
        }
        console.log(`[db] 迁移 ${data.orders.length} 个订单`);
      }
    }

    // Purchases
    const purchasesFile = path.join(dataDir, 'purchases.json');
    if (fs.existsSync(purchasesFile)) {
      const data = JSON.parse(fs.readFileSync(purchasesFile, 'utf8'));
      for (const purchase of data) {
        await this.savePurchase(purchase);
      }
      console.log(`[db] 迁移 ${data.length} 条购买记录`);
    }

    // TxLogs
    const txLogFile = path.join(dataDir, 'tx-log.json');
    if (fs.existsSync(txLogFile)) {
      const data = JSON.parse(fs.readFileSync(txLogFile, 'utf8'));
      for (const log of data) {
        await this.saveTxLog(log);
      }
      console.log(`[db] 迁移 ${data.length} 条交易日志`);
    }

    // Notifications
    const notificationsFile = path.join(dataDir, 'notifications.json');
    if (fs.existsSync(notificationsFile)) {
      const data = JSON.parse(fs.readFileSync(notificationsFile, 'utf8'));
      for (const notification of data) {
        await this.saveNotification(notification);
      }
      console.log(`[db] 迁移 ${data.length} 条通知`);
    }

    // PushSubs
    const pushSubsFile = path.join(dataDir, 'push_subs.json');
    if (fs.existsSync(pushSubsFile)) {
      const data = JSON.parse(fs.readFileSync(pushSubsFile, 'utf8'));
      for (const sub of data) {
        await this.savePushSub(sub.wallet, sub.subscription);
      }
      console.log(`[db] 迁移 ${data.length} 条推送订阅`);
    }

    // Agents
    const agentsFile = path.join(dataDir, 'agents.json');
    if (fs.existsSync(agentsFile)) {
      const data = JSON.parse(fs.readFileSync(agentsFile, 'utf8'));
      for (const agent of data) {
        await this.saveAgent(agent);
      }
      console.log(`[db] 迁移 ${data.length} 个 Agent`);
    }

    console.log('[db] 数据迁移完成');
  }

  // ── 关闭 ───────────────────────────────────────

  close() {
    if (this.db) {
      this.db.close();
    }
  }
}

// ── 导出 ────────────────────────────────────────

function createDatabase(dbPath) {
  return new Database(dbPath);
}

module.exports = { Database, createDatabase };
