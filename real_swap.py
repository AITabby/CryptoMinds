#!/usr/bin/env python3
"""
真实 PancakeSwap 买币 + 转币到买家钱包
用法: python3 real_swap.py <seller_name> <buyer_address> <amount_bnb>
"""
import sys, json, time
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from config import BSC_RPC, load_wallets, get_wallet_key, DEFAULT_SLIPPAGE_BPS

ROUTER = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E')
WBNB = Web3.to_checksum_address('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')

# 有 WBNB 流动性池的代币
TOKENS = [
    ('0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56', 'BUSD'),
    ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 'USDC'),
    ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 'USDC'),
    ('0x2170Ed0880ac9A755fd29B2688956BD959F933F8', 'ETH'),
    ('0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c', 'BTCB'),
]

ROUTER_ABI = [{
    "inputs": [
        {"internalType":"address[]","name":"path","type":"address[]"},
        {"internalType":"uint256","name":"amountOutMin","type":"uint256"},
        {"internalType":"address","name":"to","type":"address"},
        {"internalType":"uint256","name":"deadline","type":"uint256"}
    ],
    "name": "swapExactETHForTokens",
    "outputs": [{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],
    "stateMutability": "payable",
    "type": "function"
},{
    "inputs": [
        {"internalType":"uint256","name":"amountIn","type":"uint256"},
        {"internalType":"address[]","name":"path","type":"address[]"}
    ],
    "name":"getAmountsOut",
    "outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],
    "stateMutability":"view",
    "type":"function"
}]

ERC20_ABI = [
    {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
]

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 real_swap.py <seller_name> <buyer_address> <amount_bnb> [token_address]")
        print("  token_address: 可选，默认买 USDC")
        sys.exit(1)

    seller_name = sys.argv[1]
    buyer_addr = Web3.to_checksum_address(sys.argv[2])
    amount_bnb = float(sys.argv[3])
    custom_token = sys.argv[4] if len(sys.argv) >= 5 else None

    w3 = Web3(Web3.HTTPProvider(BSC_RPC))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    wallets = load_wallets()
    seller_info = wallets.get(seller_name)
    if not seller_info:
        print(json.dumps({"ok": False, "error": f"找不到卖家 {seller_name}"}))
        sys.exit(1)

    seller_key = get_wallet_key(seller_name)
    account = w3.eth.account.from_key(seller_key)
    seller_addr = account.address

    print(f"卖家: {seller_name} ({seller_addr[:10]}...)", file=sys.stderr)
    print(f"买家: {buyer_addr[:10]}...", file=sys.stderr)
    print(f"金额: {amount_bnb} BNB", file=sys.stderr)

    # 检查余额
    bal = w3.eth.get_balance(seller_addr)
    print(f"卖家余额: {w3.from_wei(bal, 'ether'):.4f} BNB", file=sys.stderr)
    if bal < w3.to_wei(amount_bnb + 0.001, 'ether'):
        # 尝试用 four_meme 代执行
        fm_key = get_wallet_key('four_meme')
        if fm_key:
            account = w3.eth.account.from_key(fm_key)
            seller_addr = account.address
            print(f"余额不足，改用 four_meme 代执行 ({seller_addr[:10]}...)", file=sys.stderr)

    # 选目标代币：自定义 > 默认USDC
    token_addr = None
    token_sym = None
    if custom_token:
        token_addr = Web3.to_checksum_address(custom_token)
        # 尝试从已知列表找符号，否则链上查
        known = {t[0].lower(): t[1] for t in TOKENS}
        token_sym = known.get(custom_token.lower())
        print(f"使用自定义代币: {custom_token[:10]}...", file=sys.stderr)
    if not token_addr:
        token_addr, token_sym = TOKENS[1]  # USDC（流动性最好）
        token_addr = Web3.to_checksum_address(token_addr)
        print(f"默认买 USDC（流动性最好，卖家Agent可选择其他代币）", file=sys.stderr)

    router = w3.eth.contract(address=ROUTER, abi=ROUTER_ABI)
    token_contract = w3.eth.contract(address=token_addr, abi=ERC20_ABI)

    # 1. Swap BNB → Token
    swap_amount = w3.to_wei(amount_bnb, 'ether')
    deadline = int(time.time()) + 300
    nonce = w3.eth.get_transaction_count(seller_addr)

    print(f"执行 swapExactETHForTokens...", file=sys.stderr)
    quoted = router.functions.getAmountsOut(swap_amount, [WBNB, token_addr]).call()
    amount_out_min = max(1, quoted[-1] * max(0, 10_000 - DEFAULT_SLIPPAGE_BPS) // 10_000)

    swap_tx = router.functions.swapExactETHForTokens(
        [WBNB, token_addr],
        amount_out_min,
        seller_addr,
        deadline
    ).build_transaction({
        'from': seller_addr,
        'value': swap_amount,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': 56,
    })

    signed_swap = account.sign_transaction(swap_tx)
    swap_hash = w3.eth.send_raw_transaction(signed_swap.raw_transaction)
    print(f"Swap TX: {swap_hash.hex()}", file=sys.stderr)

    # 等确认
    receipt = None
    for _ in range(60):
        try:
            receipt = w3.eth.get_transaction_receipt(swap_hash)
            if receipt:
                break
        except:
            pass
        time.sleep(3)

    if not receipt or receipt['status'] != 1:
        print(f"Swap 失败! status={receipt['status'] if receipt else 'null'}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": "Swap 交易失败"}))
        sys.exit(1)

    print(f"Swap 成功! gasUsed={receipt['gasUsed']}", file=sys.stderr)

    # 2. 查代币余额
    decimals = token_contract.functions.decimals().call()
    symbol = token_contract.functions.symbol().call()
    raw_balance = token_contract.functions.balanceOf(seller_addr).call()
    token_amount = raw_balance / (10 ** decimals)
    print(f"买到: {token_amount:.6f} {symbol}", file=sys.stderr)

    # 3. Transfer token to buyer
    print(f"转币给买家...", file=sys.stderr)
    transfer_nonce = w3.eth.get_transaction_count(seller_addr)
    transfer_tx = token_contract.functions.transfer(buyer_addr, raw_balance).build_transaction({
        'from': seller_addr,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'nonce': transfer_nonce,
        'chainId': 56,
    })

    signed_transfer = account.sign_transaction(transfer_tx)
    transfer_hash = w3.eth.send_raw_transaction(signed_transfer.raw_transaction)
    print(f"Transfer TX: {transfer_hash.hex()}", file=sys.stderr)

    for _ in range(60):
        try:
            t_receipt = w3.eth.get_transaction_receipt(transfer_hash)
            if t_receipt:
                break
        except:
            pass
        time.sleep(3)

    if t_receipt and t_receipt['status'] == 1:
        print(f"转币成功!", file=sys.stderr)
    else:
        print(f"转币失败!", file=sys.stderr)

    result = {
        "ok": True,
        "buy_tx": swap_hash.hex(),
        "transfer_tx": transfer_hash.hex(),
        "token_address": token_addr,
        "token_amount": f"{token_amount:.6f}",
        "token_symbol": symbol,
    }
    print(json.dumps(result))

if __name__ == '__main__':
    main()
