"""
Demo 交易流脚本 — 在 BSC 测试网上跑完整的 Escrow 场景

场景 1: 正常交易（创建→交付→确认放款）
场景 2: 争议+仲裁（创建→交付→争议→仲裁退款）
场景 3: 卖家超时（创建→超时→退款）

用法:
    python3 scripts/demo_transactions.py

需要:
    - DEPLOY_PRIVATE_KEY 已设置（合约 owner）
    - deployments/bsc-testnet.json 存在
    - 部署者钱包有足够 tBNB（>0.15）
"""

import json
import os
import sys
import time

CONTRACT_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts")
DEPLOY_DIR = os.path.join(os.path.dirname(__file__), "..", "deployments")


def load_contract():
    from web3 import Web3

    # 加载部署信息
    deploy_path = os.path.join(DEPLOY_DIR, "bsc-testnet.json")
    with open(deploy_path) as f:
        deploy = json.load(f)

    rpc = os.getenv("BSC_TESTNET_RPC", "https://data-seed-prebsc-1-s1.bnbchain.org:8545")
    w3 = Web3(Web3.HTTPProvider(rpc))
    assert w3.is_connected(), f"无法连接 {rpc}"

    # 加载 ABI
    with open(os.path.join(CONTRACT_DIR, "ServiceEscrow_sol_ServiceEscrow.abi")) as f:
        abi = json.load(f)

    contract = w3.eth.contract(address=deploy["contract_address"], abi=abi)
    return w3, contract, deploy


def send_tx(w3, account, tx_dict):
    """签名并发送交易，返回 receipt"""
    signed = account.sign_transaction(tx_dict)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return receipt


def check_balance(w3, address, label=""):
    bal = w3.from_wei(w3.eth.get_balance(address), "ether")
    if label:
        print(f"  {label}: {bal:.4f} tBNB")
    return bal


def main():
    from web3 import Web3

    w3, contract, deploy = load_contract()
    owner_key = os.getenv("DEPLOY_PRIVATE_KEY")
    if not owner_key:
        print("Error: 设置 DEPLOY_PRIVATE_KEY")
        sys.exit(1)

    owner = w3.eth.account.from_key(owner_key)
    print(f"Owner: {owner.address}")
    check_balance(w3, owner.address, "Owner 余额")

    # 创建 buyer 和 seller（从 owner 转一些 tBNB 过去）
    buyer = w3.eth.account.create()
    seller = w3.eth.account.create()
    print(f"\nBuyer: {buyer.address}")
    print(f"Seller: {seller.address}")

    # 给 buyer 和 seller 转 tBNB
    fund_amount = w3.to_wei(0.03, "ether")
    print(f"\n转 tBNB 给测试账户...")
    for acct, label in [(buyer, "Buyer"), (seller, "Seller")]:
        nonce = w3.eth.get_transaction_count(owner.address, "pending")
        tx = {
            "from": owner.address,
            "to": acct.address,
            "value": fund_amount,
            "gas": 21000,
            "gasPrice": w3.to_wei(3, "gwei"),
            "nonce": nonce,
        }
        signed = owner.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        check_balance(w3, acct.address, label)

    print(f"\n{'='*60}")
    print(f"场景 1: 正常交易（创建→交付→确认放款）")
    print(f"{'='*60}")

    # 先把超时设短一点方便 demo
    nonce = w3.eth.get_transaction_count(owner.address, "pending")
    tx = contract.functions.setTimeouts(300, 120).build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, owner, tx)
    print(f"  超时设置: 买家确认 5min, 卖家交付 2min (tx: {receipt.status})")

    # Step 1: Buyer 创建订单
    order_amount = w3.to_wei(0.01, "ether")
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = contract.functions.createOrder(
        seller.address,
        "ai-agent-data-delivery-001",
        0, 0  # 使用默认超时
    ).build_transaction({
        "from": buyer.address,
        "value": order_amount,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, buyer, tx)
    print(f"  ✓ 买家创建订单 0.01 BNB (tx: {receipt.transactionHash.hex()[:16]}...)")

    # Step 2: Seller 交付
    order_id = contract.functions.allOrderIds(0).call()
    nonce = w3.eth.get_transaction_count(seller.address, "pending")
    tx = contract.functions.deliver(
        order_id,
        "QmX7bV9kL3nR2pT5wY8jA0fD6sH4mK1cE7gN3qU9oP5i"
    ).build_transaction({
        "from": seller.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, seller, tx)
    print(f"  ✓ 卖家交付结果 (tx: {receipt.transactionHash.hex()[:16]}...)")

    # Step 3: Buyer 确认
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = contract.functions.confirm(order_id).build_transaction({
        "from": buyer.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, buyer, tx)
    print(f"  ✓ 买家确认收货，BNB 释放给卖家 (tx: {receipt.transactionHash.hex()[:16]}...)")

    # 查询订单状态
    order = contract.functions.getOrder(order_id).call()
    status_names = ["None", "Pending", "Delivering", "Delivered", "Confirmed", "Disputed", "Refunded", "Expired"]
    print(f"  订单状态: {status_names[order[8]]}")
    print(f"  托管金额: {w3.from_wei(order[3], 'ether')} BNB")

    print(f"\n{'='*60}")
    print(f"场景 2: 争议+仲裁（创建→交付→争议→仲裁退款）")
    print(f"{'='*60}")

    # Step 1: Buyer 创建订单
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = contract.functions.createOrder(
        seller.address,
        "ai-agent-compute-task-002",
        0, 0
    ).build_transaction({
        "from": buyer.address,
        "value": order_amount,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, buyer, tx)
    print(f"  ✓ 买家创建订单 0.01 BNB")

    # Step 2: Seller 交付
    order_id_2 = contract.functions.allOrderIds(1).call()
    nonce = w3.eth.get_transaction_count(seller.address, "pending")
    tx = contract.functions.deliver(
        order_id_2,
        "QmFailedDeliveryDataCorrupted"
    ).build_transaction({
        "from": seller.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, seller, tx)
    print(f"  ✓ 卖家交付（但质量有问题）")

    # Step 3: Buyer 争议
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = contract.functions.dispute(order_id_2).build_transaction({
        "from": buyer.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, buyer, tx)
    print(f"  ✓ 买家发起争议")

    # Step 4: Owner 仲裁退款
    nonce = w3.eth.get_transaction_count(owner.address, "pending")
    tx = contract.functions.arbitrateRefund(order_id_2, "Seller delivered corrupted data").build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, owner, tx)
    print(f"  ✓ 仲裁结果：退款给买家 (reason: Seller delivered corrupted data)")

    order = contract.functions.getOrder(order_id_2).call()
    print(f"  订单状态: {status_names[order[8]]}")

    print(f"\n{'='*60}")
    print(f"场景 3: 卖家超时（创建→等待超时→退款）")
    print(f"{'='*60}")

    # 把卖家超时设成极短（10秒）方便 demo
    nonce = w3.eth.get_transaction_count(owner.address, "pending")
    tx = contract.functions.setTimeouts(300, 10).build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, owner, tx)
    print(f"  卖家交付超时设为 10 秒")

    # Step 1: Buyer 创建订单
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = contract.functions.createOrder(
        seller.address,
        "ai-agent-oracle-query-003",
        0, 0
    ).build_transaction({
        "from": buyer.address,
        "value": order_amount,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, buyer, tx)
    print(f"  ✓ 买家创建订单 0.01 BNB")

    order_id_3 = contract.functions.allOrderIds(2).call()

    # Step 2: 等卖家超时
    print(f"  ⏳ 等待卖家交付超时（10秒）...")
    time.sleep(12)

    # Step 3: 任何人都可以 claim seller timeout
    nonce = w3.eth.get_transaction_count(owner.address, "pending")
    tx = contract.functions.claimSellerTimeout(order_id_3).build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    receipt = send_tx(w3, owner, tx)
    print(f"  ✓ 卖家超时，BNB 退还给买家")

    order = contract.functions.getOrder(order_id_3).call()
    print(f"  订单状态: {status_names[order[8]]}")

    # 恢复超时设置
    nonce = w3.eth.get_transaction_count(owner.address, "pending")
    tx = contract.functions.setTimeouts(259200, 86400).build_transaction({
        "from": owner.address,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.to_wei(3, "gwei"),
    })
    send_tx(w3, owner, tx)

    # 打印汇总
    print(f"\n{'='*60}")
    print(f"Demo 交易汇总")
    print(f"{'='*60}")
    total_orders = contract.functions.getOrderCount().call()
    total_escrowed = w3.from_wei(contract.functions.totalEscrowed().call(), "ether")
    total_released = w3.from_wei(contract.functions.totalReleased().call(), "ether")
    total_refunded = w3.from_wei(contract.functions.totalRefunded().call(), "ether")
    total_disputed = contract.functions.totalDisputed().call()

    print(f"  总订单数: {total_orders}")
    print(f"  累计托管: {total_escrowed} BNB")
    print(f"  累计释放: {total_released} BNB")
    print(f"  累计退款: {total_refunded} BNB")
    print(f"  累计争议: {total_disputed}")

    print(f"\n各订单状态:")
    for i in range(total_orders):
        oid = contract.functions.allOrderIds(i).call()
        order = contract.functions.getOrder(oid).call()
        print(f"  #{i+1} {order[2][:30]:30s} | {w3.from_wei(order[3], 'ether'):6.3f} BNB | {status_names[order[8]]}")

    print(f"\nBSCscan: https://testnet.bscscan.com/address/{contract.address}")


if __name__ == "__main__":
    main()
