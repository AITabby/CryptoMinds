#!/usr/bin/env python3
"""
AgentPay SDK - 智能路由引擎
扫描多链多代币余额，计算最优支付路径
"""
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# 可选依赖：web3 和 solana（用于真实余额查询）
try:
    from web3 import Web3
    from solana.rpc.api import Client as SolanaClient
    from solders.pubkey import Pubkey
except ImportError:
    # 运行时会检查依赖
    pass

# 各链配置
import os
_BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org")

CHAIN_CONFIG = {
    "bsc": {
        "name": "BNB Chain",
        "rpc": _BSC_RPC,
        "chain_id": 56,
        "explorer": "https://bscscan.com",
        "native_token": "BNB",
        "tokens": {
            "BNB": {"contract": "native", "decimals": 18},
            "USDC": {"contract": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
            "USDT": {"contract": "0x55d398326f99069fB4407F07B4826C3D12f32119", "decimals": 18}
        },
        "gas_price_gwei": 3,
        "avg_tx_fee_usd": 0.05
    },
    "base": {
        "name": "Base",
        "rpc": "https://mainnet.base.org",
        "chain_id": 8453,
        "explorer": "https://basescan.org",
        "native_token": "ETH",
        "tokens": {
            "ETH": {"contract": "native", "decimals": 18},
            "USDC": {"contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6}
        },
        "gas_price_gwei": 0.01,
        "avg_tx_fee_usd": 0.001
    },
    "solana": {
        "name": "Solana",
        "rpc": "https://api.mainnet-beta.solana.com",
        "explorer": "https://solscan.io",
        "native_token": "SOL",
        "tokens": {
            "SOL": {"contract": "native", "decimals": 9},
            "USDC": {"contract": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "decimals": 6}
        },
        "gas_price_gwei": 0,  # Solana用优先费
        "avg_tx_fee_usd": 0.001
    }
}

@dataclass
class Balance:
    """余额信息"""
    chain: str
    token: str
    amount: float  # 实际数量
    amount_usd: float  # 美元价值
    contract: str
    decimals: int

@dataclass
class PaymentPath:
    """支付路径"""
    chain: str
    token: str
    amount: float  # 需要支付的数量
    amount_usd: float  # 美元价值
    balance_available: float  # 可用余额
    gas_fee_usd: float  # 预估Gas费
    total_cost_usd: float  # 总成本（代币+Gas）
    success_probability: float  # 成功率估计
    route_type: str  # "direct" 或 "swap" 或 "bridge"
    notes: str = ""
    split_details: Optional[List[Dict]] = None

class SmartRouter:
    """智能路由引擎"""
    
    def __init__(self):
        self.chains = CHAIN_CONFIG
        # 模拟汇率（实际应从API获取）
        self.rates = {
            "BNB": 626.0,
            "ETH": 1600.0,
            "SOL": 150.0,
            "USDC": 1.0,
            "USDT": 1.0
        }

    def get_token_usd_price(self, token: str, chain: str) -> float:
        """
        获取代币的 USD 价格。
        优先使用链上 DEX 报价，失败时回退到内置估值。
        """
        if token in {"USDC", "USDT"}:
            return 1.0

        real_rate_to_usdc = self.get_dex_rate(token, "USDC", chain)
        if real_rate_to_usdc and real_rate_to_usdc > 0:
            self.rates[token] = real_rate_to_usdc
            return real_rate_to_usdc

        return self.rates.get(token, 1.0)

    def enrich_balances_with_usd(self, balances: List[Balance]) -> List[Balance]:
        """用尽量真实的 USD 价格回填余额估值。"""
        for balance in balances:
            balance.amount_usd = balance.amount * self.get_token_usd_price(balance.token, balance.chain)
        return balances
    
    def scan_balances(self, wallet_address: str) -> List[Balance]:
        """
        扫描多链多代币余额
        使用 requests 直接调用 RPC，无需额外依赖
        """
        import requests
        import json
        import sys
        
        balances = []
        
        # 遍历各链配置
        for chain_id, config in self.chains.items():
            try:
                if chain_id in ["bsc", "base"]:
                    # EVM 链：使用 JSON-RPC 查询
                    rpc_url = config["rpc"]
                    
                    # 查询原生代币余额
                    try:
                        payload = {
                            "jsonrpc": "2.0",
                            "method": "eth_getBalance",
                            "params": [wallet_address, "latest"],
                            "id": 1
                        }
                        resp = requests.post(rpc_url, json=payload, timeout=5)
                        if resp.status_code == 200:
                            result = resp.json()
                            if "result" in result:
                                balance_wei = int(result["result"], 16)
                                decimals = config["tokens"][config["native_token"]]["decimals"]
                                balance = balance_wei / (10 ** decimals)
                                usd = balance * self.rates.get(config["native_token"], 0)
                                balances.append(Balance(
                                    chain=chain_id,
                                    token=config["native_token"],
                                    amount=balance,
                                    amount_usd=usd,
                                    contract="native",
                                    decimals=decimals
                                ))
                    except Exception as e:
                        sys.stderr.write(f"警告: 查询 {config['name']} 原生余额失败: {e}")
                    
                    # 查询 ERC20 代币余额
                    for token_symbol, token_info in config["tokens"].items():
                        if token_info["contract"] == "native":
                            continue
                        try:
                            # 构造 balanceOf 调用数据
                            # balanceOf(address) 的函数选择器是 0x70a08231
                            address_padded = wallet_address[2:].lower().zfill(64)
                            data = "0x70a08231" + address_padded
                            
                            payload = {
                                "jsonrpc": "2.0",
                                "method": "eth_call",
                                "params": [{
                                    "to": token_info["contract"],
                                    "data": data
                                }, "latest"],
                                "id": 2
                            }
                            resp = requests.post(rpc_url, json=payload, timeout=5)
                            if resp.status_code == 200:
                                result = resp.json()
                                if "result" in result and result["result"] != "0x":
                                    balance_wei = int(result["result"], 16)
                                    balance = balance_wei / (10 ** token_info["decimals"])
                                    usd = balance * self.rates.get(token_symbol, 0)
                                    balances.append(Balance(
                                        chain=chain_id,
                                        token=token_symbol,
                                        amount=balance,
                                        amount_usd=usd,
                                        contract=token_info["contract"],
                                        decimals=token_info["decimals"]
                                    ))
                        except Exception as e:
                            # 静默失败，可能是代币合约不存在
                            continue
                    
                elif chain_id == "solana":
                    # Solana 链：使用 JSON-RPC 查询
                    rpc_url = config["rpc"]
                    
                    # 查询 SOL 余额
                    try:
                        payload = {
                            "jsonrpc": "2.0",
                            "method": "getBalance",
                            "params": [wallet_address],
                            "id": 1
                        }
                        resp = requests.post(rpc_url, json=payload, timeout=5)
                        if resp.status_code == 200:
                            result = resp.json()
                            if "result" in result and "value" in result["result"]:
                                lamports = result["result"]["value"]
                                balance = lamports / (10 ** config["tokens"]["SOL"]["decimals"])
                                usd = balance * self.rates.get("SOL", 0)
                                balances.append(Balance(
                                    chain=chain_id,
                                    token="SOL",
                                    amount=balance,
                                    amount_usd=usd,
                                    contract="native",
                                    decimals=config["tokens"]["SOL"]["decimals"]
                                ))
                    except Exception as e:
                        sys.stderr.write(f"警告: 查询 Solana SOL 余额失败: {e}")
                    
                    # 查询 USDC 余额（SPL 代币）
                    try:
                        # 先获取 USDC mint 地址
                        usdc_mint = config["tokens"]["USDC"]["contract"]
                        # 使用 getTokenAccountsByOwner 查询
                        payload = {
                            "jsonrpc": "2.0",
                            "method": "getTokenAccountsByOwner",
                            "params": [wallet_address, {"mint": usdc_mint}, {"encoding": "jsonParsed"}],
                            "id": 2
                        }
                        resp = requests.post(rpc_url, json=payload, timeout=5)
                        if resp.status_code == 200:
                            result = resp.json()
                            if "result" in result and "value" in result["result"]:
                                accounts = result["result"]["value"]
                                if accounts:
                                    # 取第一个账户的余额
                                    account = accounts[0]["account"]["data"]["parsed"]["info"]
                                    balance = float(account["tokenAmount"]["uiAmount"])
                                    usd = balance * self.rates.get("USDC", 0)
                                    balances.append(Balance(
                                        chain=chain_id,
                                        token="USDC",
                                        amount=balance,
                                        amount_usd=usd,
                                        contract=usdc_mint,
                                        decimals=config["tokens"]["USDC"]["decimals"]
                                    ))
                    except Exception as e:
                        # 如果没有 USDC 账户，静默失败
                        pass
                    
            except Exception as e:
                sys.stderr.write(f"警告: 处理 {chain_id} 链时出错: {e}")
                continue
        
        return self.enrich_balances_with_usd(balances)
    
    def get_gas_price(self, chain_id: str) -> Dict:
        """
        获取链的当前Gas Price（单位：Gwei）
        返回 {"success": bool, "gas_price_gwei": float, "fee_usd": float}
        """
        import requests
        
        config = self.chains.get(chain_id)
        if not config:
            return {"success": False, "error": "不支持的链"}
        
        try:
            if chain_id in ["bsc", "base"]:
                # EVM链：查询eth_gasPrice
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_gasPrice",
                    "params": [],
                    "id": 1
                }
                resp = requests.post(config["rpc"], json=payload, timeout=5)
                if resp.status_code == 200:
                    result = resp.json()
                    if "result" in result:
                        gas_price_wei = int(result["result"], 16)
                        gas_price_gwei = gas_price_wei / 1e9
                        
                        # 估算交易费用（假设21000 gas单位，简单转账）
                        gas_units = 21000
                        fee_wei = gas_price_wei * gas_units
                        # 转换为美元价值
                        native_token = config["native_token"]
                        native_price_usd = self.get_token_usd_price(native_token, chain_id)
                        fee_usd = (fee_wei / 1e18) * native_price_usd
                        
                        return {
                            "success": True,
                            "gas_price_gwei": gas_price_gwei,
                            "fee_usd": fee_usd,
                            "chain": chain_id,
                            "native_token": native_token
                        }
            
            elif chain_id == "solana":
                # Solana：查询优先费（简化处理）
                # 实际应调用getRecentPrioritizationFees
                # 这里返回默认值
                return {
                    "success": True,
                    "gas_price_gwei": 0,  # Solana不使用gas
                    "fee_usd": 0.001,  # 固定费用
                    "chain": chain_id,
                    "native_token": "SOL"
                }
                
        except Exception as e:
            # 查询失败，返回默认值
            pass
        
        # 降级到配置中的默认值
        return {
            "success": False,
            "gas_price_gwei": config.get("gas_price_gwei", 0),
            "fee_usd": config.get("avg_tx_fee_usd", 0.05),
            "chain": chain_id,
            "native_token": config.get("native_token", "unknown")
        }
    
    def get_dex_quote(self, from_token: str, to_token: str, amount: float, chain: str) -> Optional[float]:
        """
        从 DEX 获取真实报价（返回目标代币数量），失败返回 None
        支持 BSC (PancakeSwap) 和 Base (Uniswap V2)
        """
        import requests

        router_addresses = {
            "bsc": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
            "base": "0x327Df1E6de05895d2ab08513aaDD9313Fe505d86",  # Uniswap V2 on Base
        }

        # 代币地址映射
        token_map = {
            "bsc": {
                "BNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
                "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
                "USDT": "0x55d398326f99069fB4407F07B4826C3D12f32119",
            },
            "base": {
                "ETH": "0x4200000000000000000000000000000000000006",  # WETH
                "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            },
        }

        decimals_map = {
            "bsc": {"BNB": 18, "USDC": 18, "USDT": 18},
            "base": {"ETH": 18, "USDC": 6},
        }

        if chain not in router_addresses:
            return None
        if chain not in token_map:
            return None
        if from_token not in token_map[chain] or to_token not in token_map[chain]:
            return None

        router = router_addresses[chain]
        from_addr = token_map[chain][from_token]
        to_addr = token_map[chain][to_token]
        from_decimals = decimals_map[chain][from_token]

        # 计算 amountIn (最小单位)
        amount_in_wei = hex(int(amount * (10 ** from_decimals)))

        # ABI 编码 getAmountsOut(uint256,address[])
        # 函数选择器: 0xd06ca61f
        amount_in_padded = amount_in_wei[2:].zfill(64)
        path_offset = "0000000000000000000000000000000000000000000000000000000000000040"
        path_len = "0000000000000000000000000000000000000000000000000000000000000002"
        path0 = from_addr[2:].lower().zfill(64)
        path1 = to_addr[2:].lower().zfill(64)
        calldata = f"0xd06ca61f{amount_in_padded}{path_offset}{path_len}{path0}{path1}"

        rpc_url = self.chains[chain]["rpc"]
        try:
            resp = requests.post(rpc_url, json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": router, "data": calldata}, "latest"],
                "id": 1
            }, timeout=5)
            if resp.status_code == 200:
                result = resp.json()
                if "result" in result and result["result"] != "0x":
                    hex_str = result["result"][2:]
                    # 解析 ABI 编码的 uint256[]
                    # 结构: offset(32 bytes) | length(32 bytes) | element[0](32 bytes) | element[1](32 bytes) | ...
                    if len(hex_str) >= 128:
                        arr_offset = int(hex_str[0:64], 16)  # 通常=0x20=32
                        arr_len = int(hex_str[64:128], 16)
                        if arr_len >= 2:
                            # amounts[1] 是输出金额（最后一跳）
                            out_start = 128 + (arr_len - 1) * 64
                            if len(hex_str) >= out_start + 64:
                                amount_out_wei = int(hex_str[out_start:out_start+64], 16)
                                to_decimals = decimals_map[chain][to_token]
                                return amount_out_wei / (10 ** to_decimals)
        except Exception:
            pass
        return None

    def get_dex_rate(self, from_token: str, to_token: str, chain: str) -> Optional[float]:
        """获取真实 DEX 兑换率（1 from_token = ? to_token）"""
        quote = self.get_dex_quote(from_token, to_token, 1.0, chain)
        if quote and quote > 0:
            return quote
        return None
    
    def get_swap_quote(self, from_token: str, to_token: str, amount: float, chain: str) -> Dict:
        """
        获取兑换报价（模拟，使用固定汇率）
        返回兑换所需金额和费用
        """
        # 固定汇率（实际应从DEX获取）
        rates = {
            ("BNB", "USDC"): 626.0,
            ("BNB", "USDT"): 626.0,
            ("USDC", "BNB"): 1/626.0,
            ("USDT", "BNB"): 1/626.0,
            ("SOL", "USDC"): 150.0,
            ("USDC", "SOL"): 1/150.0,
            ("ETH", "USDC"): 1600.0,
            ("USDC", "ETH"): 1/1600.0,
        }
        
        rate = rates.get((from_token, to_token))
        if not rate:
            return {"success": False, "error": "不支持的兑换对"}
        
        # 计算兑换数量
        to_amount = amount * rate
        
        # 模拟滑点 0.5%
        slippage = 0.005
        min_to_amount = to_amount * (1 - slippage)
        
        # 模拟兑换费用 0.3%（PancakeSwap费用）
        swap_fee = amount * 0.003
        
        return {
            "success": True,
            "from_token": from_token,
            "to_token": to_token,
            "from_amount": amount,
            "to_amount": to_amount,
            "min_to_amount": min_to_amount,
            "rate": rate,
            "swap_fee": swap_fee,
            "slippage": slippage,
            "chain": chain,
            "dex": "PancakeSwap" if chain == "bsc" else "Uniswap" if chain == "base" else "Raydium"
        }
    
    def calculate_paths(self, wallet_address: str, service_prices: Dict[str, float], reputation_scores: Optional[Dict[str, float]] = None, seller_agent: Optional[str] = None) -> List[PaymentPath]:
        """
        计算所有可能的支付路径
        service_prices: {"BNB_BSC": 0.0005, "USDC_BSC": 0.15, ...}
        reputation_scores: {"tiedan": 0.67, "choudan": 0.83, ...} agent名→归一化声誉分
        """
        balances = self.scan_balances(wallet_address)
        paths = []
        
        # 为每个卖家价格创建支付路径
        for price_key, price_amount in service_prices.items():
            # 解析价格键：TOKEN_CHAIN
            if "_" in price_key:
                token, chain = price_key.rsplit("_", 1)
                chain = chain.lower()  # 转换为小写以匹配余额中的chain
            else:
                # 默认链
                token = price_key
                chain = "bsc" if token in ["BNB", "USDC", "USDT"] else "solana"
            
            # 查找该链该代币的余额
            balance = next((b for b in balances if b.chain == chain and b.token == token), None)
            if not balance:
                continue
            
            # 检查余额是否足够
            if balance.amount >= price_amount:
                # 直接支付路径
                gas_info = self.get_gas_price(chain)
                gas_fee = gas_info.get('fee_usd', self.chains[chain]["avg_tx_fee_usd"])

                token_usd_price = self.get_token_usd_price(token, chain)

                total_cost = price_amount * token_usd_price + gas_fee
                success_prob = 0.95  # 余额足够，成功率高

                path = PaymentPath(
                    chain=chain,
                    token=token,
                    amount=price_amount,
                    amount_usd=price_amount * token_usd_price,
                    balance_available=balance.amount,
                    gas_fee_usd=gas_fee,
                    total_cost_usd=total_cost,
                    success_probability=success_prob,
                    route_type="direct",
                    notes=f"直接支付，余额充足"
                )
                paths.append(path)
            else:
                # 余额不足，先尝试拆分支付（从多个链组合）
                split_paths = []
                # 收集所有链上同种代币的余额
                all_balances = [b for b in balances if b.token == token]
                if all_balances:
                    # 按余额美元价值排序
                    all_balances.sort(key=lambda x: x.amount_usd, reverse=True)
                    total_balance_usd = sum(b.amount_usd for b in all_balances)
                    token_usd_price = self.get_token_usd_price(token, chain)
                    price_usd = price_amount * token_usd_price
                    
                    if total_balance_usd >= price_usd:
                        # 余额足够拆分支付
                        remaining_usd = price_usd
                        selected_chains = []
                        for balance in all_balances:
                            if remaining_usd <= 0:
                                break
                            if balance.amount_usd > 0:
                                # 该链可支付的金额
                                pay_usd = min(balance.amount_usd, remaining_usd)
                                # 计算该链需要支付的代币数量
                                pay_amount = pay_usd / token_usd_price
                                # 检查该链余额是否足够
                                if balance.amount >= pay_amount:
                                    selected_chains.append({
                                        'chain': balance.chain,
                                        'amount': pay_amount,
                                        'amount_usd': pay_usd,
                                        'balance': balance.amount
                                    })
                                    remaining_usd -= pay_usd
                        
                        if remaining_usd <= 0:
                            # 计算总Gas费（各链Gas费之和）
                            total_gas_fee = 0
                            for chain_info in selected_chains:
                                gas_info = self.get_gas_price(chain_info['chain'])
                                total_gas_fee += gas_info.get('fee_usd', self.chains[chain_info['chain']]['avg_tx_fee_usd'])
                            
                            total_cost = price_usd + total_gas_fee
                            notes = "拆分支付: " + ", ".join([f"{c['chain']}支付{c['amount']:.4f}" for c in selected_chains])
                            
                            path = PaymentPath(
                                chain="multi",
                                token=token,
                                amount=price_amount,
                                amount_usd=price_usd,
                                balance_available=total_balance_usd / token_usd_price,
                                gas_fee_usd=total_gas_fee,
                                total_cost_usd=total_cost,
                                success_probability=max(0.7, 0.95 - len(selected_chains) * 0.05),  # 根据拆分链数量调整成功率
                                route_type="split",
                                notes=notes,
                                split_details=selected_chains
                            )
                            split_paths.append(path)
                
                # 如果有拆分路径，添加到paths
                if split_paths:
                    paths.extend(split_paths)
                else:
                    # 否则先查找兑换路径（同一链上）
                    swap_paths = []
                    # 获取该链上其他代币的余额
                    other_balances = [b for b in balances if b.chain == chain and b.token != token]
                    for other_balance in other_balances:
                        # 优先使用真实 DEX 报价，降级到硬编码汇率
                        real_rate = self.get_dex_rate(other_balance.token, token, chain)
                        if real_rate and real_rate > 0:
                            rate = real_rate
                            rate_source = "链上 DEX"
                        else:
                            from_price = self.get_token_usd_price(other_balance.token, chain)
                            to_price = self.get_token_usd_price(token, chain)
                            if not from_price or not to_price:
                                continue
                            rate = from_price / to_price
                            rate_source = "估算"
                        # 需要多少 other_balance.token 来兑换 price_amount 的 token
                        needed_other_amount = price_amount / rate
                        # 加上兑换费用 0.3%（PancakeSwap/Uniswap 费用）
                        swap_fee = needed_other_amount * 0.003
                        needed_other_amount_with_fee = needed_other_amount + swap_fee
                        if other_balance.amount >= needed_other_amount_with_fee:
                            # 创建兑换路径
                            gas_info = self.get_gas_price(chain)
                            gas_fee = gas_info.get('fee_usd', self.chains[chain]["avg_tx_fee_usd"])
                            total_cost = (needed_other_amount_with_fee * self.get_token_usd_price(other_balance.token, chain)) + gas_fee
                            
                            # 模拟滑点 0.5%
                            slippage = 0.005
                            
                            path = PaymentPath(
                                chain=chain,
                                token=token,
                                amount=price_amount,
                                amount_usd=price_amount * self.get_token_usd_price(token, chain),
                                balance_available=other_balance.amount,
                                gas_fee_usd=gas_fee,
                                total_cost_usd=total_cost,
                                success_probability=0.90,  # 兑换成功率较高
                                route_type="swap",
                                notes=f"用{other_balance.token}兑换，滑点{slippage*100}%，汇率{rate:.4f}({rate_source})"
                            )
                            swap_paths.append(path)
                    
                    # 如果有兑换路径，添加到paths
                    if swap_paths:
                        paths.extend(swap_paths)
                    else:
                        # 否则查找桥接路径
                        # 假设桥接费用为 0.1 美元
                        bridge_fee_usd = 0.1

                        # 遍历其他链的同种代币余额
                        for other_balance in balances:
                            if other_balance.token == token and other_balance.chain != chain:
                                # 检查其他链余额是否足够支付价格 + 桥接费用
                                # 将桥接费用转换为代币数量（假设代币价格相同）
                                price_in_usd = price_amount * self.get_token_usd_price(token, chain)
                                total_needed_usd = price_in_usd + bridge_fee_usd
                                other_balance_usd = other_balance.amount_usd

                                if other_balance_usd >= total_needed_usd:
                                    # 创建桥接路径
                                    # 桥接后目标链的代币数量
                                    amount_after_bridge = price_amount  # 桥接不损失代币
                                    # 总成本 = 价格 + 桥接费 + 目标链Gas费
                                    gas_info = self.get_gas_price(chain)
                                    gas_fee = gas_info.get('fee_usd', self.chains[chain]["avg_tx_fee_usd"])
                                    total_cost = price_in_usd + bridge_fee_usd + gas_fee

                                    path = PaymentPath(
                                        chain=chain,
                                        token=token,
                                        amount=amount_after_bridge,
                                        amount_usd=price_in_usd,
                                        balance_available=other_balance.amount,
                                        gas_fee_usd=gas_fee,
                                        total_cost_usd=total_cost,
                                        success_probability=0.85,  # 桥接成功率较低
                                        route_type="bridge",
                                        notes=f"从{self.chains[other_balance.chain]['name']}桥接，桥接费${bridge_fee_usd}"
                                    )
                                    paths.append(path)
        
        # 声誉调整：按当前 service 对应的 seller agent 调整 success_probability
        if reputation_scores and seller_agent:
            seller_score = None
            candidate_keys = [seller_agent]
            if isinstance(seller_agent, str):
                normalized = seller_agent.strip()
                candidate_keys.extend([normalized.lower(), normalized.upper()])

            for key in candidate_keys:
                if key in reputation_scores:
                    seller_score = reputation_scores[key]
                    break

            if seller_score is None and isinstance(seller_agent, str):
                seller_key = seller_agent.strip().lower()
                for key, value in reputation_scores.items():
                    if isinstance(key, str) and key.strip().lower() == seller_key:
                        seller_score = value
                        break

            if seller_score is not None:
                for p in paths:
                    # rep=0.5 时不加成，低于 0.5 降权，高于 0.5 升权
                    rep_factor = 0.8 + 0.4 * seller_score  # 范围 0.8~1.2
                    p.success_probability = max(0.0, min(1.0, p.success_probability * rep_factor))
        
        # 按总成本排序
        paths.sort(key=lambda x: x.total_cost_usd)
        return paths
    
    def recommend_best_path(self, paths: List[PaymentPath], reputation_scores: Optional[Dict[str, float]] = None) -> Optional[PaymentPath]:
        """推荐最优路径（综合成本、成功率、声誉）"""
        if not paths:
            return None
        
        # 综合评分：成本低 + 成功率高 + 声誉高
        max_cost = max(p.total_cost_usd for p in paths) or 1
        scored = []
        for p in paths:
            cost_score = 1 - (p.total_cost_usd / max_cost)  # 0~1，越高越好
            prob_score = p.success_probability  # 已经是 0~1，且已被声誉调整过
            total = cost_score * 0.4 + prob_score * 0.6  # 声誉已通过 prob_score 体现
            scored.append((total, p))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    
    def format_recommendation(self, path: PaymentPath) -> Dict:
        """格式化推荐结果"""
        # 处理多链拆分支付
        if path.chain == "multi":
            chain_name = "多链拆分"
            explorer_url = ""
        else:
            chain_name = self.chains[path.chain]["name"]
            explorer_url = self.chains[path.chain]["explorer"]
        return {
            "chain": path.chain,
            "chain_name": chain_name,
            "symbol": path.token,
            "amount": path.amount,
            "amount_usd": path.amount_usd,
            "total_cost_usd": round(path.total_cost_usd, 4),
            "gas_fee_usd": round(path.gas_fee_usd, 4),
            "success_probability": path.success_probability,
            "route_type": path.route_type,
            "notes": path.notes,
            "explorer_url": explorer_url,
            "split_details": path.split_details or []
        }

# 测试代码
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="智能路由引擎")
    parser.add_argument("--wallet", required=True, help="钱包地址")
    parser.add_argument("--service", required=True, help="卖家ID")
    args = parser.parse_args()
    
    # 从 sellers.json 加载卖家价格
    import json
    services_path = Path(__file__).resolve().parent.parent / "sellers.json"
    try:
        with open(services_path, 'r', encoding="utf-8") as f:
            services = json.load(f)
        service = next((s for s in services if s["id"] == args.service), None)
        if not service:
            print(json.dumps({"success": False, "error": f"卖家 {args.service} 不存在"}))
            sys.exit(1)
        
        service_prices = service.get("prices", {})
        if not service_prices:
            # BNB 统一定价
            service_prices = {
                "BNB_BSC": service.get("price", 0),
            }
    except Exception as e:
        print(json.dumps({"success": False, "error": f"加载卖家失败: {str(e)}"}))
        sys.exit(1)
    
    # 加载声誉数据
    reputation_scores = {}
    try:
        rep_file = Path(__file__).resolve().parent.parent / 'agents' / 'reputation_data.json'
        if rep_file.exists():
            with open(rep_file, 'r', encoding='utf-8') as f:
                rep_data = json.load(f)
                # 数据在 agents 子键下
                agents_data = rep_data.get('agents', rep_data)
                for agent, info in agents_data.items():
                    if isinstance(info, dict):
                        reputation_scores[agent] = min(info.get('reputation_score', 50) / 100.0, 1.0)
    except Exception:
        pass
    
    router = SmartRouter()
    seller_agent = service.get("expert") or service.get("agent") or service.get("seller")
    paths = router.calculate_paths(
        args.wallet,
        service_prices,
        reputation_scores=reputation_scores,
        seller_agent=seller_agent,
    )
    
    # 转换为可序列化格式
    routes = []
    for path in paths:
        routes.append(router.format_recommendation(path))
    
    recommended = None
    best = router.recommend_best_path(paths, reputation_scores=reputation_scores)
    if best:
        recommended = router.format_recommendation(best)
    
    result = {
        "success": True,
        "wallet": args.wallet,
        "service": args.service,
        "routes": routes,
        "recommended": recommended,
        "total_routes": len(routes)
    }
    
    print(json.dumps(result, indent=2))
