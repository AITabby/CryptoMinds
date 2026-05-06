# CryptoMinds 灾难恢复标准操作程序 (SOP)

## 适用范围

本 SOP 覆盖 CryptoMinds 生产环境的关键故障场景和恢复流程。

---

## 1. PostgreSQL 崩溃恢复

### 1.1 检测

- Prometheus alert: `CryptoMindsPostgresDown` (PG 不可达 > 2 分钟)
- docker-compose: `docker ps` 显示 postgres 容器非 running
- Python API 日志: `psycopg2.OperationalError: connection refused`

### 1.2 恢复步骤

```bash
# 1. 检查容器状态
docker ps -a | grep postgres

# 2. 查看崩溃日志
docker logs cryptominds-postgres --tail 100

# 3. 重启 PG 容器
docker-compose restart postgres

# 4. 等待 PG 可用 (健康检查通过)
docker-compose ps | grep postgres

# 5. 验证数据完整性
docker exec cryptominds-postgres psql -U cryptominds -c "SELECT count(*) FROM escrow_orders;"

# 6. 重启依赖服务
docker-compose restart python-api web-api

# 7. 验证 API 可用
curl -f http://localhost:3457/healthz
curl -f http://localhost:3458/healthz
```

### 1.3 PG 数据损坏 (需要 pg_dump 恢复)

```bash
# 如果 PG 数据目录损坏:
# 1. 停止所有服务
docker-compose down

# 2. 从备份恢复 pgdata volume (需要定期 pg_dump)
docker exec cryptominds-postgres pg_dump -U cryptominds cryptominds > /backups/cryptominds_$(date +%Y%m%d).sql

# 3. 重建 PG volume
docker volume rm cryptominds_pgdata
docker-compose up -d postgres

# 4. 导入备份
cat /backups/cryptominds_YYYYMMDD.sql | docker exec -i cryptominds-postgres psql -U cryptominds cryptominds

# 5. 重启服务
docker-compose up -d
```

---

## 2. SQLite 恢复 (开发/Demo 模式)

### 2.1 检测

- Python API 返回 500 + `sqlite3.OperationalError`
- SQLite WAL 文件异常大 (> 100MB)
- 数据库文件锁定

### 2.2 恢复步骤

```bash
# 1. 检查 WAL 文件大小
ls -la web/cryptominds.db web/cryptominds.db-wal web/cryptominds.db-shm

# 2. 如果 WAL 过大, 强制 checkpoint
python3 -c "
import sqlite3
conn = sqlite3.connect('web/cryptominds.db')
conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
conn.close()
"

# 3. 从自动备份恢复 (如果数据库损坏)
ls -la web/backups/
# 选择最近的备份
cp web/backups/cryptominds_YYYYMMDD_HHMMSS.db web/cryptominds.db

# 4. 重启服务
make start
```

### 2.3 备份确认

- 自动备份线程每 `DB_BACKUP_INTERVAL_SECONDS` (默认 3600s = 1小时) 创建备份
- 保留最近 10 份备份在 `web/backups/`
- 进程退出时自动执行 WAL checkpoint

---

## 3. Express API 不可用

### 3.1 检测

- Prometheus alert: `CryptoMindsExpressDown`
- `curl http://localhost:3457/healthz` 返回非 200

### 3.2 恢复步骤

```bash
# 1. 检查进程
docker logs cryptominds-web --tail 50

# 2. 重启
docker-compose restart web-api

# 3. 如果反复崩溃, 检查 Node.js 内存
docker stats cryptominds-web

# 4. 如果是内存问题, 增加 NODE_OPTIONS
# 在 docker-compose.yml 中添加:
# NODE_OPTIONS: "--max-old-space-size=512"
```

---

## 4. Python API 不可用

### 4.1 检测

- Prometheus alert: `CryptoMindsServiceDown`
- Express 代理返回 `Python API 服务不可用`

### 4.2 恢复步骤

```bash
# 1. 检查进程
docker logs cryptominds-python --tail 50

# 2. 如果是数据库连接失败, 先修 PG (参见 §1)
# 3. 如果是依赖库缺失
pip install -r requirements.txt

# 4. 重启
docker-compose restart python-api

# 5. 如果 gunicorn worker 崩溃
# 增加 workers 或 timeout:
# GUNICORN_WORKERS=4
# GUNICORN_THREADS=8
```

---

## 5. Escrow 争议堆积

### 5.1 检测

- Prometheus alert: `CryptoMindsEscrowDisputed` (> 5 个争议订单)
- `/api/v1/protocol/escrow/disputed` 返回大量争议订单

### 5.2 处理步骤

```bash
# 1. 获取争议列表
curl -H 'X-Admin-Secret: YOUR_SECRET' http://localhost:3457/api/v1/protocol/escrow/disputed

# 2. 对每个争议进行仲裁
curl -X POST -H 'X-Admin-Secret: YOUR_SECRET' \
  -H 'Content-Type: application/json' \
  http://localhost:3457/api/v1/protocol/escrow/{id}/resolve \
  -d '{"decision":"buyer_win","reason":"卖家未交付"}'

# 3. 如果有链上订单, 确认链上仲裁已执行
# buyer_win → arbitrateRefund (自动触发)
# seller_win → arbitrateRelease (自动触发)
```

---

## 6. 私钥泄露应急

### 6.1 检测

- 发现 wallets.json 或 WALLET_ENCRYPTION_KEY 泄露
- 发现链上异常转账

### 6.2 应急步骤

```bash
# 1. 立即停止所有服务
docker-compose down
make stop

# 2. 如果使用了 WALLET_ENCRYPTION_KEY:
#    更换加密密钥, 重新加密钱包文件
python3 -c "
from agentpay_sdk.multi_chain_wallet import MultiChainWallet
import os
os.environ['WALLET_ENCRYPTION_KEY'] = 'NEW_KEY_HERE'
w = MultiChainWallet('wallets.json')
w.save_wallets()
"

# 3. 如果私钥已泄露到链上:
#    立即将所有资金转移到新钱包 (这是最紧急的操作)
#    使用新钱包重新注册 Agent

# 4. 更新所有环境变量中的密钥
#    ADMIN_SECRET, WALLET_ENCRYPTION_KEY, CRYPTOMINDS_INTERNAL_TOKEN

# 5. 重新启动
docker-compose up -d
```

---

## 7. 数据完整性验证

定期 (建议每日) 执行:

```bash
# 1. Escrow 状态一致性检查
python3 -c "
from data.sqlite_store import SqliteEscrowStore
from settlement.escrow_state import EscrowState
store = SqliteEscrowStore('web/cryptominds.db')
# 所有终态订单不应有后续转换
for order in store._orders.values():
    if order.state in (EscrowState.RELEASED, EscrowState.RESOLVED_REFUND, 
                       EscrowState.RESOLVED_RELEASE, EscrowState.EXPIRED, 
                       EscrowState.REFUNDED_TIMEOUT):
        print(f'终态订单 {order.escrow_id}: {order.state.value}')
"

# 2. Voucher 累计消费检查
python3 -c "
from data.sqlite_store import SqliteVoucherStore
store = SqliteVoucherStore('web/cryptominds.db')
for v in store._vouchers.values():
    if v.units_used > v.total_units:
        print(f'超额消费! Voucher {v.voucher_id}: used={v.units_used} > total={v.total_units}')
"

# 3. Session Key 过期检查
python3 -c "
import time
from data.sqlite_store import SqliteSessionKeyStore
store = SqliteSessionKeyStore('web/cryptominds.db')
now = int(time.time())
for k in store._keys.values():
    if k.expires_at < now and not k.revoked:
        print(f'过期未撤销! SK {k.session_key_id}: expired at {k.expires_at}')
"
```

---

## 8. 定期备份计划

| 组件 | 方式 | 频率 | 保留 |
|------|------|------|------|
| PostgreSQL | `pg_dump` | 每日 02:00 | 30 天 |
| SQLite | 自动线程 | 每小时 | 10 份 |
| wallets.json | `cp` (加密版) | 每日 | 7 天 |
| .env | `cp` | 每日 | 7 天 |
| 合约 ABI | Git | 每次部署 | 永久 |

```bash
# PG 定期备份 cron (添加到宿主机 crontab)
0 2 * * * docker exec cryptominds-postgres pg_dump -U cryptominds cryptominds | gzip > /backups/pg_cryptominds_$(date +\%Y\%m\%d).sql.gz
```

---

## 联系方式

- 管理员: GitHub Issues
- 紧急: 查看 Prometheus alerts → Grafana dashboard → 本 SOP