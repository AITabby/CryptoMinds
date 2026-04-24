#!/usr/bin/env python3
"""
CryptoMinds 真实买币执行器
两种路径：
1. four.meme bonding curve（未毕业代币）
2. PancakeSwap V2（已毕业代币）
"""
import sys, json, time
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from config import BSC_RPC, WALLETS_FILE, DEFAULT_SLIPPAGE_BPS

w3 = Web3(Web3.HTTPProvider(BSC_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
WBNB = Web3.to_checksum_address('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')

# four.meme Token Manager (proxy)
FOUR_MEME_MGR = Web3.to_checksum_address('0x5c952063c7fc8610FFDB798152D69F0B9550762b')

# PancakeSwap V2 Router
PCS_ROUTER = Web3.to_checksum_address('0x10ED43C718714eb63d5aA57B78B54704E256024E')

# ---- ABIs ----
BUY_TOKEN_AMAP_ABI = [{
    "inputs": [
        {"internalType": "uint256", "name": "origin", "type": "uint256"},
        {"internalType": "address", "name": "token", "type": "address"},
        {"internalType": "uint256", "name": "funds", "type": "uint256"},
        {"internalType": "uint256", "name": "minAmount", "type": "uint256"}
    ],
    "name": "buyTokenAMAP",
    "outputs": [],
    "stateMutability": "payable",
    "type": "function"
}]

SELL_TOKEN_ABI = [{
    "inputs": [
        {"internalType": "address", "name": "token", "type": "address"},
        {"internalType": "uint256", "name": "amount", "type": "uint256"}
    ],
    "name": "sellToken",
    "outputs": [],
    "stateMutability": "payable",
    "type": "function"
}]

PCS_SWAP_ABI = [{
    "inputs": [
        {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
        {"internalType": "address[]", "name": "path", "type": "address[]"},
        {"internalType": "address", "name": "to", "type": "address"},
        {"internalType": "uint256", "name": "deadline", "type": "uint256"}
    ],
    "name": "swapExactETHForTokensSupportingFeeOnTransferTokens",
    "outputs": [],
    "stateMutability": "payable",
    "type": "function"
}]

PCS_QUOTE_ABI = [{
    "inputs": [
        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
        {"internalType": "address[]", "name": "path", "type": "address[]"}
    ],
    "name": "getAmountsOut",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "view",
    "type": "function"
}]

ERC20_ABI = [
    {"inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

# PancakeSwap V2 Factory
PCS_FACTORY = Web3.to_checksum_address('0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73')
FACTORY_ABI = [{"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view","type":"function"}]


def apply_slippage(raw_amount, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """根据滑点 BPS 计算最小可接受输出。"""
    return max(1, raw_amount * max(0, 10_000 - slippage_bps) // 10_000)


def is_graduated(token_addr):
    """检查代币是否已毕业（有 PancakeSwap V2 池子）"""
    token_cs = Web3.to_checksum_address(token_addr)
    factory = w3.eth.contract(address=PCS_FACTORY, abi=FACTORY_ABI)
    pair = factory.functions.getPair(WBNB, token_cs).call()
    return pair != '0x0000000000000000000000000000000000000000'


def buy_on_fourmeme(seller_key, seller_addr, buyer_addr, token_addr, bnb_amount):
    """在 four.meme bonding curve 上买币"""
    token_cs = Web3.to_checksum_address(token_addr)
    mgr = w3.eth.contract(address=FOUR_MEME_MGR, abi=BUY_TOKEN_AMAP_ABI)
    
    funds_wei = w3.to_wei(bnb_amount, 'ether')
    nonce = w3.eth.get_transaction_count(seller_addr)
    # four.meme 当前脚本里没有可靠 quote ABI，先避免把 minAmount 彻底设为 0。
    min_amount = 1
    
    # origin=0 表示标准买币
    tx = mgr.functions.buyTokenAMAP(
        0,  # origin
        token_cs,
        funds_wei,
        min_amount
    ).build_transaction({
        'from': seller_addr,
        'value': funds_wei,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': 56,
    })
    
    signed = w3.eth.account.sign_transaction(tx, seller_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Four.meme 买币 TX: {tx_hash.hex()}")
    
    # 等确认
    receipt = wait_receipt(tx_hash)
    if receipt and receipt.status == 1:
        print(f"✅ Four.meme 买币成功! Gas used: {receipt.gasUsed}")
        return tx_hash.hex(), receipt
    else:
        print(f"❌ Four.meme 买币失败!")
        return None, None


def buy_on_pancakeswap(seller_key, seller_addr, buyer_addr, token_addr, bnb_amount):
    """在 PancakeSwap V2 买币（已毕业代币）"""
    token_cs = Web3.to_checksum_address(token_addr)
    router = w3.eth.contract(address=PCS_ROUTER, abi=PCS_SWAP_ABI + PCS_QUOTE_ABI)
    
    bnb_wei = w3.to_wei(bnb_amount, 'ether')
    nonce = w3.eth.get_transaction_count(seller_addr)
    quoted = router.functions.getAmountsOut(bnb_wei, [WBNB, token_cs]).call()
    amount_out_min = apply_slippage(quoted[-1])
    
    tx = router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
        amount_out_min,
        [WBNB, token_cs],
        seller_addr,  # 先买给自己，再转给买家
        9999999999,
    ).build_transaction({
        'from': seller_addr,
        'value': bnb_wei,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': 56,
    })
    
    signed = w3.eth.account.sign_transaction(tx, seller_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"PancakeSwap 买币 TX: {tx_hash.hex()}")
    
    receipt = wait_receipt(tx_hash)
    if receipt and receipt.status == 1:
        print(f"✅ PancakeSwap 买币成功! Gas used: {receipt.gasUsed}")
        return tx_hash.hex(), receipt
    else:
        print(f"❌ PancakeSwap 买币失败!")
        return None, None


def transfer_tokens(seller_key, seller_addr, buyer_addr, token_addr, amount_raw):
    """将代币从卖家转到买家钱包"""
    token_cs = Web3.to_checksum_address(token_addr)
    token_contract = w3.eth.contract(address=token_cs, abi=ERC20_ABI)

    amount_raw = int(amount_raw or 0)
    if amount_raw <= 0:
        print("本次买入新增代币为 0，跳过转账")
        return None
    
    # ERC20 transfer
    TRANSFER_ABI = [{"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]
    token_with_transfer = w3.eth.contract(address=token_cs, abi=TRANSFER_ABI)
    
    nonce = w3.eth.get_transaction_count(seller_addr)
    buyer_cs = Web3.to_checksum_address(buyer_addr)
    
    tx = token_with_transfer.functions.transfer(buyer_cs, amount_raw).build_transaction({
        'from': seller_addr,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': 56,
    })
    
    signed = w3.eth.account.sign_transaction(tx, seller_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"代币转账 TX: {tx_hash.hex()}")
    
    receipt = wait_receipt(tx_hash)
    if receipt and receipt.status == 1:
        symbol = '?'
        try:
            symbol = token_contract.functions.symbol().call()
        except:
            pass
        dec = 18
        try:
            dec = token_contract.functions.decimals().call()
        except:
            pass
        readable = amount_raw / (10 ** dec)
        print(f"✅ 转账成功! {readable:.4f} {symbol} → 买家")
        return tx_hash.hex(), receipt, amount_raw
    else:
        print(f"❌ 转账失败!")
        return None


def wait_receipt(tx_hash, timeout=180):
    for _ in range(timeout // 3):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                return receipt
        except:
            pass
        time.sleep(3)
    return None


def execute_buy(seller_name, buyer_addr, token_addr, bnb_amount):
    """
    主入口：执行真实买币
    seller_name: 钱包名 (gangdan, choudan 等)
    buyer_addr: 买家钱包地址
    token_addr: 代币合约地址
    bnb_amount: BNB 数量 (如 0.001)
    """
    wallets = json.load(open(WALLETS_FILE))
    seller_info = wallets[seller_name]
    seller_addr = Web3.to_checksum_address(seller_info['address'])
    key = seller_info.get('private_key') or seller_info.get('privateKey')
    if not key.startswith('0x'):
        key = '0x' + key
    buyer_cs = Web3.to_checksum_address(buyer_addr)
    token_cs = Web3.to_checksum_address(token_addr)
    token_contract = w3.eth.contract(address=token_cs, abi=ERC20_ABI)
    
    # 查卖家余额
    bal = w3.eth.get_balance(seller_addr)
    print(f"卖家: {seller_name} ({seller_addr[:10]}...)")
    print(f"买家: {buyer_cs[:10]}...")
    print(f"代币: {token_cs}")
    print(f"金额: {bnb_amount} BNB")
    print(f"卖家余额: {w3.from_wei(bal, 'ether'):.6f} BNB")
    
    seller_token_before = token_contract.functions.balanceOf(seller_addr).call()

    # 判断路径
    graduated = is_graduated(token_cs)
    
    if graduated:
        print(f"📊 代币已毕业 → PancakeSwap V2 路径")
        swap_hash, swap_receipt = buy_on_pancakeswap(key, seller_addr, buyer_cs, token_cs, bnb_amount)
    else:
        print(f"📊 代币未毕业 → four.meme bonding curve 路径")
        swap_hash, swap_receipt = buy_on_fourmeme(key, seller_addr, buyer_cs, token_cs, bnb_amount)
    
    if not swap_hash:
        return {"ok": False, "error": "买币失败"}
    
    # 等一下让链上状态更新
    time.sleep(3)
    seller_token_after = token_contract.functions.balanceOf(seller_addr).call()
    purchased_amount = max(0, seller_token_after - seller_token_before)
    
    # 转代币给买家
    transfer_result = transfer_tokens(key, seller_addr, buyer_cs, token_cs, purchased_amount)
    if transfer_result:
        transfer_hash, transfer_receipt, transferred_amount = transfer_result
    else:
        transfer_hash, transfer_receipt, transferred_amount = None, None, 0
    
    if not transfer_hash:
        return {"ok": False, "error": "买币成功但转账失败", "swapHash": swap_hash}
    
    # 查买家最终余额
    buyer_bal = token_contract.functions.balanceOf(buyer_cs).call()
    symbol = '?'
    dec = 18
    try:
        symbol = token_contract.functions.symbol().call()
        dec = token_contract.functions.decimals().call()
    except:
        pass
    readable = transferred_amount / (10 ** dec)
    
    result = {
        "ok": True,
        "token": token_cs,
        "symbol": symbol,
        "amount": readable,
        "bnbSpent": bnb_amount,
        "swapHash": swap_hash,
        "transferHash": transfer_hash,
        "graduated": graduated,
        "path": "PancakeSwap" if graduated else "four.meme"
    }
    print(f"\n🎉 交易完成!")
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("用法: python3 token_buyer.py <seller_name> <buyer_addr> <token_addr> [bnb_amount]")
        print("示例: python3 token_buyer.py gangdan 0xd2f899CE... 0x3518d7aee5248b9307b8a82b7c3fa49e073c4444 0.001")
        sys.exit(1)
    
    seller = sys.argv[1]
    buyer = sys.argv[2]
    token = sys.argv[3]
    amount = float(sys.argv[4]) if len(sys.argv) > 4 else 0.001
    
    result = execute_buy(seller, buyer, token, amount)
    print(json.dumps(result))
