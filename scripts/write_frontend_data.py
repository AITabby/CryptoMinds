"""
写入前端展示数据到 SQLite

填充 sellers、orders、purchases、agents、escrow_orders 表，
让前端页面有丰富的内容展示。
"""

import sqlite3, time, json, uuid, os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "web", "cryptominds.db")
NOW = int(time.time())

# Wallets from BSC testnet test
BUYER_WALLET = "0x9a0141704724e0D0A9cE2F12d7542C55E1371195"
SELLER_WALLETS = [
    ("0x0E3D78C4B6fA5adb24d8Be4FC72eFd79Dd5B1cBA", "AI-Alpha", "AI量化策略引擎，BSC链上实时数据分析与代币推荐", "0.03"),
    ("0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18", "DataOracle", "去中心化数据预言机，链上链下数据聚合服务", "0.05"),
    ("0x5C4B8a2D7E1F9bA6C8e3D4F5A6B7c8D9E0F1A2B3", "NeuralNet", "神经网络模型推理服务，支持图像/文本/语音AI分析", "0.04"),
]

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    # === Sellers ===
    print("Inserting sellers...")
    for wallet, name, desc, fee in SELLER_WALLETS:
        cur.execute("""INSERT OR REPLACE INTO sellers
            (wallet, name, desc, deposit, fee_rate, strategy, rating,
             total_orders, bad_ratings, active_orders, sales,
             status, service_status, endpoint, agent_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (wallet, name, desc, 5.0, float(fee), "AI-driven market analysis",
             4.5 + len(name) % 2 * 0.3, 3 + len(name), 0, 0, 5 + len(name) * 2,
             "approved", "approved", f"https://{name.lower()}.cryptominds.cc/api",
             "自主", time.strftime("%Y-%m-%dT%H:%M:%SZ"), time.strftime("%Y-%m-%dT%H:%M:%SZ")))

    # === Agents ===
    print("Inserting agents...")
    agent_skills = [
        [{"task_type": "market_analysis", "verification_gate": "data_quality", "supported_chains": ["bsc"], "available": True, "base_price": "0.001"}],
        [{"task_type": "data_oracle", "verification_gate": "accuracy", "supported_chains": ["bsc"], "available": True, "base_price": "0.001"}],
        [{"task_type": "ai_inference", "verification_gate": "model_output", "supported_chains": ["bsc"], "available": True, "base_price": "0.001"}],
    ]
    for i, (wallet, name, desc, fee) in enumerate(SELLER_WALLETS):
        cur.execute("""INSERT OR REPLACE INTO agents
            (id, wallet, name, description, endpoint, framework, skills,
             active, online, fee_rate, deposit, staked,
             reputation_score, tasks_completed, tasks_failed, total_volume, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.lower(), wallet, name, desc,
             f"https://{name.lower()}.cryptominds.cc/api",
             "generic", json.dumps(agent_skills[i]),
             1, 1, float(fee), 5.0, "2.0",
             75.0 + i * 5, 10 + i * 3, 1, "0.5", time.strftime("%Y-%m-%dT%H:%M:%SZ")))

    # === Orders + Purchases (from testnet transactions) ===
    print("Inserting orders and purchases...")
    order_scenarios = [
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "ai-data-001", "service_name": "AI量化分析",
         "amount": 0.001, "status": "completed", "seller_idx": 0, "state": "verified",
         "tx_hash": "0xb15fa0493dbdb5..."},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "ai-task-002", "service_name": "数据预言机",
         "amount": 0.001, "status": "refunded", "seller_idx": 1, "state": "resolved_refund",
         "tx_hash": "0x57f669816ae552...", "dispute": "Corrupted data"},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "ai-oracle-003", "service_name": "AI推理服务",
         "amount": 0.001, "status": "expired", "seller_idx": 2, "state": "expired",
         "tx_hash": "0xddfa51a41ab7bb..."},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "ai-missing-004", "service_name": "AI量化分析",
         "amount": 0.001, "status": "refunded_timeout", "seller_idx": 0, "state": "refunded_timeout",
         "tx_hash": "0x896ae1427dc210..."},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "ai-premium-005", "service_name": "高级AI策略",
         "amount": 0.001, "status": "completed", "seller_idx": 1, "state": "resolved_release",
         "tx_hash": "0x4a656ab95c228b..."},
        # More historical orders for volume
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "market-scan-006", "service_name": "市场扫描",
         "amount": 0.002, "status": "completed", "seller_idx": 0, "state": "verified",
         "tx_hash": "0xabc123def456..."},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "data-feed-007", "service_name": "数据流订阅",
         "amount": 0.003, "status": "completed", "seller_idx": 2, "state": "verified",
         "tx_hash": "0x789abc012345..."},
        {"id": f"ord-{uuid.uuid4().hex[:8]}", "service_id": "nlp-task-008", "service_name": "NLP文本分析",
         "amount": 0.001, "status": "disputed", "seller_idx": 1, "state": "disputed",
         "tx_hash": "0xdef789ghi012..."},
    ]

    for o in order_scenarios:
        seller_w, seller_n, seller_d, seller_fee = SELLER_WALLETS[o["seller_idx"]]
        fee_amount = o["amount"] * float(seller_fee)
        ts = NOW - (8 - order_scenarios.index(o)) * 3600
        is_completed = o["status"] in ("completed", "verified")

        # Order (seller perspective)
        cur.execute("""INSERT OR REPLACE INTO orders
            (id, buyer_wallet, seller_wallet, amount, fee, total_paid,
             status, tx_hash, token_address, token_amount, rating, input,
             created_at, delivered_at, completed_at, timeout_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (o["id"], BUYER_WALLET, seller_w, o["amount"], fee_amount,
             o["amount"] + fee_amount, o["status"], o["tx_hash"],
             "", "", 5 if is_completed else None,
             json.dumps({"service": o["service_name"], "chain": "bsc"}),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts + 300)) if is_completed else None,
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts + 600)) if is_completed else None,
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts + 7200))))

        # Purchase (buyer perspective)
        cur.execute("""INSERT OR REPLACE INTO purchases
            (id, service_id, service_name, buyer_wallet, buyer_name,
             expert_wallet, expert_name, price, status, payment_mode,
             payment_hash, payment_verified, payment_from, payment_to,
             payment_value, payment_block, payment_demo, tx_hash, input,
             report, rating, escrow_order_id,
             created_at, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (o["id"], o["service_id"], o["service_name"], BUYER_WALLET, "TestBuyer",
             seller_w, seller_n, o["amount"], o["status"], "escrow",
             o["tx_hash"], 1, BUYER_WALLET, seller_w,
             str(o["amount"]), 12345678, 1, o["tx_hash"],
             json.dumps({"task": o["service_id"]}),
             json.dumps({"result": f"AI output for {o['service_id']}"}) if is_completed else "",
             5 if is_completed else None, f"esc-{o['id']}",
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts + 600)) if is_completed else None))

    # === Escrow Orders (matching on-chain data) ===
    print("Inserting escrow orders...")
    chain_order_ids = [
        "ai-data-001", "ai-task-002", "ai-oracle-003", "ai-missing-004", "ai-premium-005"
    ]
    escrow_states = ["verified", "resolved_refund", "expired", "refunded_timeout", "resolved_release"]
    for i, (svc, state) in enumerate(zip(chain_order_ids, escrow_states)):
        seller_w = SELLER_WALLETS[i % 3][0]
        seller_n = SELLER_WALLETS[i % 3][1]
        esc_id = f"esc-testnet-{i+1}"
        ts = NOW - (5 - i) * 3600

        cur.execute("""INSERT OR REPLACE INTO escrow_orders
            (escrow_id, task_id, order_id, buyer_wallet, seller_wallet,
             seller_agent_id, amount, channel_id, chain,
             on_chain_order_id, state, created_at, funded_at,
             delivered_at, verified_at, disputed_at, resolved_at,
             seller_timeout_at, buyer_timeout_at,
             dispute_reason, dispute_initiator,
             arbitration_weight_buyer, arbitration_weight_seller,
             resolution, resolution_reason,
             verification_score, verification_threshold,
             dispute_window_seconds, evidence, chain_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (esc_id, svc, "", BUYER_WALLET, seller_w,
             seller_n.lower(), "0.001", "bsc-native", "bsc",
             "", state, ts, ts + 10,
             ts + 300 if state not in ("refunded_timeout",) else 0,
             ts + 600 if state == "verified" else 0,
             ts + 400 if state in ("resolved_refund", "resolved_release") else 0,
             ts + 500 if state in ("resolved_refund", "resolved_release") else 0,
             ts + 120, ts + 120,
             "Corrupted data" if state == "resolved_refund" else "Unfair dispute" if state == "resolved_release" else "",
             "buyer" if state in ("resolved_refund", "resolved_release") else "",
             0.3 if state == "resolved_refund" else 0.7 if state == "resolved_release" else 0,
             0.7 if state == "resolved_refund" else 0.3 if state == "resolved_release" else 0,
             "buyer_win" if state == "resolved_refund" else "seller_win" if state == "resolved_release" else "",
             "",  # resolution_reason
             0.85 if state == "verified" else 0, 0.7,
             172800, "", 1))

    # === Performance Records ===
    print("Inserting performance records...")
    record_statuses = ["settled", "settled", "failed", "failed", "settled"]
    for i, (svc, rec_status) in enumerate(zip(chain_order_ids, record_statuses)):
        seller_w = SELLER_WALLETS[i % 3][0]
        seller_n = SELLER_WALLETS[i % 3][1]
        rec_id = f"rec-testnet-{i+1}"
        ts = NOW - (5 - i) * 3600

        cur.execute("""INSERT OR REPLACE INTO performance_records
            (record_id, task_id, task_type, buyer_wallet, seller_wallet,
             seller_agent_id, chain, amount, status, success,
             score, created_at, completed_at, response_time_ms,
             payment_tx, payment_amount, evidence,
             disputed, dispute_reason, resolution)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec_id, svc, "market_analysis", BUYER_WALLET, seller_w,
             seller_n.lower(), "bsc", "0.001", rec_status,
             1 if rec_status == "settled" else 0,
             0.85 if rec_status == "settled" else 0.3, ts, ts + 600,
             2500 + i * 500,
             f"0x{uuid.uuid4().hex[:16]}...", "0.001",
             json.dumps({"verification": "auto", "chain": "bsc"}),
             1 if rec_status == "failed" else 0,
             "data quality issue" if rec_status == "failed" else "",
             "refund" if rec_status == "failed" else ""))

    # === Notifications ===
    print("Inserting notifications...")
    notifications = [
        ("Order confirmed — AI-Alpha delivered market analysis", "order", "ai-data-001", "AI量化分析"),
        ("Escrow released — 0.001 BNB sent to DataOracle", "payment", "ai-premium-005", "高级AI策略"),
        ("Dispute resolved — refund processed for task ai-task-002", "dispute", "ai-task-002", "数据预言机"),
        ("New seller registered — NeuralNet now available", "system", "", ""),
        ("Buyer timeout claimed — funds released to seller", "order", "ai-oracle-003", "AI推理服务"),
    ]
    for i, (msg, ntype, svc, svc_name) in enumerate(notifications):
        nid = i + 100
        cur.execute("""INSERT OR REPLACE INTO notifications
            (id, type, target_wallet, order_id, service_id, service_name,
             buyer_wallet, buyer_name, seller_wallet, seller_name,
             input, read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nid, ntype, BUYER_WALLET,
             f"ord-{nid}", svc, svc_name,
             BUYER_WALLET, "TestBuyer",
             SELLER_WALLETS[i % 3][0], SELLER_WALLETS[i % 3][1],
             msg, 0, NOW - i * 1800))

    # === Tx Logs ===
    print("Inserting tx logs...")
    tx_types = ["createOrder", "deliver", "confirm", "dispute", "arbitrateRefund",
                "claimBuyerTimeout", "claimSellerTimeout", "arbitrateRelease"]
    for i, tx_type in enumerate(tx_types):
        seller_w, seller_n, _, _ = SELLER_WALLETS[i % 3]
        cur.execute("""INSERT OR REPLACE INTO tx_logs
            (id, tx, from_wallet, from_name, to_wallet, to_name,
             amount, reason, verified, receipt, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i + 200, f"0x{uuid.uuid4().hex[:32]}",
             BUYER_WALLET, "TestBuyer", seller_w, seller_n,
             "0.001", tx_type, 1,
             json.dumps({"status": "confirmed", "gasUsed": 30000 + i * 5000}),
             NOW - i * 600))

    db.commit()

    # Summary
    print("\n=== 数据写入完成 ===")
    for table in ["sellers", "agents", "orders", "purchases", "escrow_orders",
                  "performance_records", "notifications", "tx_logs"]:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")

    db.close()

if __name__ == "__main__":
    main()