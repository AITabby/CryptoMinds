#!/usr/bin/env node
/**
 * JSON → SQLite 数据迁移脚本
 *
 * 用法: node migrate_to_sqlite.js
 */

const path = require('path');
const { Database } = require('./lib/database');

async function main() {
  const dataDir = path.join(__dirname, '..');  // JSON files in project root
  const dbPath = path.join(__dirname, 'cryptominds.db');

  console.log('=== CryptoMinds 数据迁移 ===\n');
  console.log('数据目录:', dataDir);
  console.log('数据库路径:', dbPath);
  console.log('');

  const db = new Database(dbPath);

  try {
    console.log('[1/2] 初始化数据库...');
    await db.init();

    console.log('[2/2] 迁移 JSON 数据...');
    await db.migrateFromJson(dataDir);

    console.log('\n=== 迁移完成 ===');
    console.log('数据库文件:', dbPath);

    // 验证
    const sellers = await db.getSellers();
    const purchases = await db.getPurchases();
    const txLogs = await db.getTxLogs();
    const notifications = await db.getNotifications('0x');

    console.log('\n验证:');
    console.log('  卖家:', sellers.length);
    console.log('  购买记录:', purchases.length);
    console.log('  交易日志:', txLogs.length);

  } catch (err) {
    console.error('迁移失败:', err);
    process.exit(1);
  } finally {
    db.close();
  }
}

main();