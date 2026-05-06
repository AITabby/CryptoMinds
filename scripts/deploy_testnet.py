"""
部署 ServiceEscrow 合约到 BSC 测试网

用法:
    python3 scripts/deploy_testnet.py [--private-key KEY] [--rpc URL]

环境变量:
    DEPLOY_PRIVATE_KEY  部署者私钥（或用 --private-key）
    BSC_TESTNET_RPC     测试网 RPC（默认 BNB Chain 官方）
"""

import json
import os
import sys
import time

def main():
    from web3 import Web3

    rpc = os.getenv("BSC_TESTNET_RPC", "https://data-seed-prebsc-1-s1.bnbchain.org:8545")
    private_key = os.getenv("DEPLOY_PRIVATE_KEY") or None

    # Parse args
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--private-key" and i + 1 < len(args):
            private_key = args[i + 1]
            i += 2
        elif args[i] == "--rpc" and i + 1 < len(args):
            rpc = args[i + 1]
            i += 2
        else:
            i += 1

    if not private_key:
        print("Error: 需要提供部署私钥")
        print("  设置环境变量 DEPLOY_PRIVATE_KEY 或使用 --private-key")
        print()
        print("步骤:")
        print("  1. 用 MetaMask 创建一个新的测试钱包（不要用主网钱包！）")
        print("  2. 从水龙头领取 tBNB: https://www.bnbchain.org/en/testnet-faucet")
        print("  3. 导出私钥，设置 DEPLOY_PRIVATE_KEY=xxx")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print(f"Error: 无法连接到 {rpc}")
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    balance = w3.eth.get_balance(account.address)
    balance_bnb = w3.from_wei(balance, "ether")

    print(f"网络: BSC Testnet (Chain ID: {w3.eth.chain_id})")
    print(f"部署者: {account.address}")
    print(f"余额: {balance_bnb:.4f} tBNB")

    if balance_bnb < 0.01:
        print(f"\n余额不足！需要至少 0.01 tBNB")
        print(f"领取: https://www.bnbchain.org/en/testnet-faucet")
        sys.exit(1)

    # 加载编译产物
    contract_dir = os.path.join(os.path.dirname(__file__), "..", "contracts")
    abi_path = os.path.join(contract_dir, "ServiceEscrow_sol_ServiceEscrow.abi")
    bin_path = os.path.join(contract_dir, "ServiceEscrow_sol_ServiceEscrow.bin")

    with open(abi_path) as f:
        abi = json.load(f)
    with open(bin_path) as f:
        bytecode = "0x" + f.read().strip()

    # 构造合约
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # 构造参数：买家确认超时 3 天，卖家交付超时 1 天
    default_timeout = 3 * 24 * 3600  # 3 days
    seller_timeout = 1 * 24 * 3600   # 1 day

    print(f"\n部署参数:")
    print(f"  买家确认超时: {default_timeout // 3600}h")
    print(f"  卖家交付超时: {seller_timeout // 3600}h")
    print(f"\n部署中...")

    # 估算 gas
    gas_estimate = contract.constructor(default_timeout, seller_timeout).estimate_gas({"from": account.address})
    gas_limit = int(gas_estimate * 1.2)
    print(f"  Gas 估算: {gas_estimate:,} (限制: {gas_limit:,})")

    # 发送部署交易
    tx = contract.constructor(default_timeout, seller_timeout).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": gas_limit,
        "gasPrice": w3.to_wei(3, "gwei"),
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  交易哈希: {tx_hash.hex()}")

    # 等待确认
    print(f"  等待确认...", end="", flush=True)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f" 完成!")

    if receipt.status != 1:
        print(f"Error: 部署失败！")
        sys.exit(1)

    contract_address = receipt.contractAddress
    cost_bnb = w3.from_wei(receipt.gasUsed * receipt.effectiveGasPrice, "ether")

    print(f"\n{'='*50}")
    print(f"部署成功！")
    print(f"{'='*50}")
    print(f"合约地址: {contract_address}")
    print(f"区块号: {receipt.blockNumber}")
    print(f"Gas 使用: {receipt.gasUsed:,}")
    print(f"费用: {cost_bnb:.6f} tBNB")
    print(f"BSCscan: https://testnet.bscscan.com/address/{contract_address}")

    # 保存部署信息
    deploy_info = {
        "network": "bsc-testnet",
        "chain_id": w3.eth.chain_id,
        "contract_address": contract_address,
        "deployer": account.address,
        "tx_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "cost_bnb": float(cost_bnb),
        "deployed_at": int(time.time()),
        "constructor_args": {
            "default_timeout": default_timeout,
            "seller_timeout": seller_timeout,
        },
    }

    deploy_dir = os.path.join(os.path.dirname(__file__), "..", "deployments")
    os.makedirs(deploy_dir, exist_ok=True)
    deploy_path = os.path.join(deploy_dir, "bsc-testnet.json")
    with open(deploy_path, "w") as f:
        json.dump(deploy_info, f, indent=2)
    print(f"\n部署信息已保存: {deploy_path}")

    # 验证合约可读
    deployed = w3.eth.contract(address=contract_address, abi=abi)
    owner = deployed.functions.owner().call()
    dt = deployed.functions.defaultTimeout().call()
    st = deployed.functions.sellerTimeout().call()
    print(f"\n合约验证:")
    print(f"  owner: {owner}")
    print(f"  defaultTimeout: {dt}s ({dt // 3600}h)")
    print(f"  sellerTimeout: {st}s ({st // 3600}h)")

    # 生成 .env 片段
    print(f"\n将以下内容添加到 .env:")
    print(f"ESCROW_CONTRACT_ADDRESS={contract_address}")
    print(f"BSC_TESTNET_RPC={rpc}")


if __name__ == "__main__":
    main()
