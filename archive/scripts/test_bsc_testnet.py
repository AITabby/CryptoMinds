"""
BSC 测试网合约测试脚本

5 个场景覆盖 ServiceEscrow V2 完整流程。
需要 DEPLOY_PRIVATE_KEY 环境变量（部署者私钥，需有 tBNB）。

用法:
    export DEPLOY_PRIVATE_KEY=你的私钥
    python3 scripts/test_bsc_testnet.py

领 tBNB: https://testnet.bscscan.com/faucet
"""

import json, os, sys, time

BSC_TESTNET_RPC = os.getenv("BSC_TESTNET_RPC", "https://data-seed-prebsc-1-s1.bnbchain.org:8545")
ESCROW_ADDRESS = "0xe9C878845F7299C00Ff6465B02f43De2a1b49b62"
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
ABI_PATH = os.path.join(PROJECT_DIR, "build", "contracts_ServiceEscrow_sol_ServiceEscrow.abi")
STATUS = ["None", "Pending", "Delivering", "Delivered", "Confirmed", "Disputed", "Refunded", "Expired"]


def main():
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    from eth_account import Account

    w3 = Web3(Web3.HTTPProvider(BSC_TESTNET_RPC, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    assert w3.is_connected(), f"Cannot connect to {BSC_TESTNET_RPC}"

    with open(ABI_PATH) as f:
        abi = json.load(f)
    contract = w3.eth.contract(address=ESCROW_ADDRESS, abi=abi)

    pk = os.getenv("DEPLOY_PRIVATE_KEY")
    if not pk:
        print("Error: set DEPLOY_PRIVATE_KEY")
        sys.exit(1)

    buyer = Account.from_key(pk)
    # Generate a fresh random seller account each run (avoids drained Hardhat keys)
    seller = Account.create()
    print(f"Buyer:  {buyer.address} ({w3.from_wei(w3.eth.get_balance(buyer.address), 'ether'):.4f} tBNB)")
    print(f"Seller: {seller.address} (new, funding...)")

    def send(account, tx_dict, label=""):
        signed = account.sign_transaction(tx_dict)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        ok = "OK" if receipt.status == 1 else "FAIL"
        print(f"  {label}: {ok} (gas={receipt.gasUsed}, tx={receipt.transactionHash.hex()[:14]}...)")
        if receipt.status != 1:
            raise Exception(f"TX failed: {label}")
        return receipt

    def build(from_addr, func_call, value=0, nonce=None):
        if nonce is None:
            nonce = w3.eth.get_transaction_count(from_addr, "pending")
        return func_call.build_transaction({
            "from": from_addr, "nonce": nonce, "value": value,
            "gas": 500000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": 97,
        })

    # Fund seller
    nonce = w3.eth.get_transaction_count(buyer.address, "pending")
    tx = {"from": buyer.address, "to": seller.address, "value": w3.to_wei(0.01, "ether"),
          "gas": 50000, "gasPrice": w3.to_wei(1, "gwei"),
          "nonce": nonce, "chainId": 97}
    send(buyer, tx, "Fund seller")
    print(f"  Seller: {w3.from_wei(w3.eth.get_balance(seller.address), 'ether'):.4f} tBNB")

    order_amount = w3.to_wei(0.001, "ether")
    start_idx = contract.functions.getOrderCount().call()
    print(f"  Existing orders: {start_idx}")

    # Set short timeouts
    print(f"\n{'='*60}\nSetup: setTimeouts(120s, 120s)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.setTimeouts(120, 120)), "setTimeouts")

    # === Scene 1: Normal ===
    print(f"\n{'='*60}\n场景 1: 正常交易 (创建→交付→确认放款)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.createOrder(seller.address, "ai-data-001", 0, 0), order_amount), "Buyer creates order")
    oid = contract.functions.allOrderIds(start_idx).call()
    send(seller, build(seller.address, contract.functions.deliver(oid, "QmResult001")), "Seller delivers")
    send(buyer, build(buyer.address, contract.functions.confirm(oid)), "Buyer confirms -> BNB to seller")

    # === Scene 2: Dispute + refund ===
    print(f"\n{'='*60}\n场景 2: 争议+仲裁退款 (创建→交付→争议→仲裁退款)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.createOrder(seller.address, "ai-task-002", 0, 0), order_amount), "Buyer creates order")
    oid2 = contract.functions.allOrderIds(start_idx + 1).call()
    send(seller, build(seller.address, contract.functions.deliver(oid2, "QmBadData")), "Seller delivers")
    send(buyer, build(buyer.address, contract.functions.dispute(oid2)), "Buyer disputes")
    send(buyer, build(buyer.address, contract.functions.arbitrateRefund(oid2, "Corrupted data")), "Owner: refund to buyer")

    # === Scene 3: Buyer timeout ===
    print(f"\n{'='*60}\n场景 3: 买家超时 (创建→交付→等待→claimBuyerTimeout)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.createOrder(seller.address, "ai-oracle-003", 0, 0), order_amount), "Buyer creates order")
    oid3 = contract.functions.allOrderIds(start_idx + 2).call()
    send(seller, build(seller.address, contract.functions.deliver(oid3, "QmOracleResult")), "Seller delivers")
    print("  Waiting 125s for buyer timeout...")
    time.sleep(125)
    send(buyer, build(buyer.address, contract.functions.claimBuyerTimeout(oid3)), "claimBuyerTimeout -> BNB to seller")

    # === Scene 4: Seller timeout ===
    print(f"\n{'='*60}\n场景 4: 卖家超时 (创建→等待→claimSellerTimeout)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.createOrder(seller.address, "ai-missing-004", 0, 0), order_amount), "Buyer creates order")
    oid4 = contract.functions.allOrderIds(start_idx + 3).call()
    print("  Waiting 125s for seller timeout...")
    time.sleep(125)
    send(buyer, build(buyer.address, contract.functions.claimSellerTimeout(oid4)), "claimSellerTimeout -> BNB to buyer")

    # === Scene 5: Dispute + release ===
    print(f"\n{'='*60}\n场景 5: 争议+仲裁放款 (创建→交付→争议→仲裁放款)\n{'='*60}")
    send(buyer, build(buyer.address, contract.functions.createOrder(seller.address, "ai-premium-005", 0, 0), order_amount), "Buyer creates order")
    oid5 = contract.functions.allOrderIds(start_idx + 4).call()
    send(seller, build(seller.address, contract.functions.deliver(oid5, "QmPremiumResult")), "Seller delivers")
    send(buyer, build(buyer.address, contract.functions.dispute(oid5)), "Buyer disputes (unfairly)")
    send(buyer, build(buyer.address, contract.functions.arbitrateRelease(oid5)), "Owner: release to seller")

    # Restore timeouts
    send(buyer, build(buyer.address, contract.functions.setTimeouts(86400, 1800)), "Restore timeouts")

    # Summary
    print(f"\n{'='*60}\nSummary\n{'='*60}")
    total = contract.functions.getOrderCount().call()
    print(f"  Orders: {total}")
    print(f"  Escrowed: {w3.from_wei(contract.functions.totalEscrowed().call(), 'ether'):.4f} tBNB")
    print(f"  Released: {w3.from_wei(contract.functions.totalReleased().call(), 'ether'):.4f} tBNB")
    print(f"  Refunded: {w3.from_wei(contract.functions.totalRefunded().call(), 'ether'):.4f} tBNB")
    print(f"  Disputed: {contract.functions.totalDisputed().call()}")
    for i in range(start_idx, total):
        oid = contract.functions.allOrderIds(i).call()
        o = contract.functions.getOrder(oid).call()
        print(f"    #{i} {o[2][:30]:30s} | {w3.from_wei(o[3],'ether'):6.4f} | {STATUS[o[8]]}")
    print(f"\n  https://testnet.bscscan.com/address/{ESCROW_ADDRESS}")

if __name__ == "__main__":
    main()
