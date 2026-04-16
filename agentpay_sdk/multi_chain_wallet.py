#!/usr/bin/env python3
"""
AgentPay SDK - 多链钱包管理
统一管理 BSC, Base, Solana 等多链钱包
"""

import json
import os
from typing import Dict, Optional, List
from dataclasses import dataclass
from pathlib import Path

# 尝试导入各链库
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

try:
    from solana.rpc.api import Client as SolanaClient
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False

@dataclass
class WalletInfo:
    """钱包信息"""
    chain: str
    address: str
    private_key: Optional[str] = None  # ⚠️ 仅内存中使用，绝不写入日志/文件/网络
    balance: Optional[float] = None
    token_balances: Optional[Dict] = None
    
    def to_dict(self, include_private: bool = False) -> Dict:
        data = {
            "chain": self.chain,
            "address": self.address,
            "balance": self.balance,
            "token_balances": self.token_balances
        }
        if include_private and self.private_key:
            import warnings
            warnings.warn(
                "⚠️ private_key is being serialized! "
                "Ensure this data is never logged, persisted, or sent over the network.",
                stacklevel=2
            )
            data["private_key"] = self.private_key
        return data

class MultiChainWallet:
    """多链钱包管理器"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        "bsc": {
            "rpc": os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org"),
            "chain_id": 56,
            "explorer": "https://bscscan.com"
        },
        "base": {
            "rpc": "https://mainnet.base.org",
            "chain_id": 8453,
            "explorer": "https://basescan.org"
        },
        "solana": {
            "rpc": "https://api.mainnet-beta.solana.com",
            "explorer": "https://solscan.io"
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.expanduser("~/.hermes/profiles/goudan/wallets.json")
        self.config = self.DEFAULT_CONFIG.copy()
        self.wallets = {}
        self.clients = {}
        
        # 加载钱包
        self.load_wallets()
    
    def load_wallets(self):
        """加载钱包配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    # 适配现有格式：{agent_name: {address, private_key}}
                    for agent_name, wallet_data in data.items():
                        if isinstance(wallet_data, dict) and 'address' in wallet_data:
                            # 假设现有钱包是 BSC 的
                            self.wallets[f"bsc_{agent_name}"] = WalletInfo(
                                chain="bsc",
                                address=wallet_data['address'],
                                private_key=wallet_data.get('private_key')
                            )
                print(f"✅ 加载了 {len(self.wallets)} 个钱包")
            except Exception as e:
                print(f"⚠️  加载钱包失败: {e}")
        else:
            print(f"⚠️  钱包文件不存在: {self.config_path}")
    
    def save_wallets(self):
        """保存钱包配置"""
        try:
            # 转换为现有格式
            data = {}
            for key, wallet in self.wallets.items():
                if wallet.chain == "bsc":  # 只保存 BSC 钱包以兼容
                    agent_name = key.replace("bsc_", "")
                    data[agent_name] = {
                        "address": wallet.address,
                        "private_key": wallet.private_key
                    }
            
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✅ 保存了 {len(data)} 个钱包")
        except Exception as e:
            print(f"❌ 保存钱包失败: {e}")
    
    def get_wallet(self, chain: str, agent_name: str) -> Optional[WalletInfo]:
        """获取指定链和代理的钱包"""
        key = f"{chain}_{agent_name}"
        return self.wallets.get(key)
    
    def create_wallet(self, chain: str, agent_name: str) -> WalletInfo:
        """创建新钱包"""
        key = f"{chain}_{agent_name}"
        
        if chain in ["bsc", "base"]:
            if not WEB3_AVAILABLE:
                raise ImportError("web3.py 未安装")
            
            # 创建以太坊风格钱包
            account = Web3().eth.account.create()
            wallet = WalletInfo(
                chain=chain,
                address=account.address,
                private_key=account.key.hex()
            )
        elif chain == "solana":
            if not SOLANA_AVAILABLE:
                raise ImportError("solana-py 未安装")
            
            # 创建 Solana 钱包
            keypair = Keypair()
            wallet = WalletInfo(
                chain=chain,
                address=str(keypair.pubkey()),
                private_key=bytes(keypair).hex()
            )
        else:
            raise ValueError(f"不支持的链: {chain}")
        
        self.wallets[key] = wallet
        self.save_wallets()
        return wallet
    
    def get_balance(self, chain: str, agent_name: str, 
                   token: Optional[str] = None) -> float:
        """获取余额"""
        wallet = self.get_wallet(chain, agent_name)
        if not wallet:
            raise ValueError(f"钱包不存在: {chain}_{agent_name}")
        
        if chain in ["bsc", "base"]:
            return self._get_evm_balance(wallet, token)
        elif chain == "solana":
            return self._get_solana_balance(wallet, token)
        else:
            raise ValueError(f"不支持的链: {chain}")
    
    def _get_evm_balance(self, wallet: WalletInfo, token: Optional[str] = None) -> float:
        """获取 EVM 链余额"""
        if not WEB3_AVAILABLE:
            return 0.0
        
        chain = wallet.chain
        if chain not in self.clients:
            from web3.middleware import ExtraDataToPOAMiddleware
            w3 = Web3(Web3.HTTPProvider(self.config[chain]['rpc']))
            # BSC 是 POA 链，web3 v7 必须加此 middleware
            if chain == "bsc":
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            self.clients[chain] = w3
        
        w3 = self.clients[chain]
        
        if token:
            # ERC20 代币余额
            # TODO: 实现代币余额查询
            return 0.0
        else:
            # 原生代币余额
            try:
                balance_wei = w3.eth.get_balance(wallet.address)
                return float(Web3.from_wei(balance_wei, 'ether'))
            except Exception as e:
                print(f"⚠️  获取余额失败: {e}")
                return 0.0
    
    def _get_solana_balance(self, wallet: WalletInfo, token: Optional[str] = None) -> float:
        """获取 Solana 余额"""
        if not SOLANA_AVAILABLE:
            return 0.0
        
        chain = "solana"
        if chain not in self.clients:
            self.clients[chain] = SolanaClient(self.config[chain]['rpc'])
        
        client = self.clients[chain]
        
        try:
            pubkey = Pubkey.from_string(wallet.address)
            if token:
                # SPL 代币余额
                # TODO: 实现代币余额查询
                return 0.0
            else:
                # SOL 余额
                response = client.get_balance(pubkey)
                return response.value / 1e9  # 转换为 SOL
        except Exception as e:
            print(f"⚠️  获取 Solana 余额失败: {e}")
            return 0.0
    
    def transfer(self, from_chain: str, from_agent: str, 
                to_address: str, amount: float, 
                token: Optional[str] = None) -> str:
        """转账"""
        wallet = self.get_wallet(from_chain, from_agent)
        if not wallet:
            raise ValueError(f"钱包不存在: {from_chain}_{from_agent}")
        
        if from_chain in ["bsc", "base"]:
            return self._evm_transfer(wallet, to_address, amount, token)
        elif from_chain == "solana":
            return self._solana_transfer(wallet, to_address, amount, token)
        else:
            raise ValueError(f"不支持的链: {from_chain}")
    
    def _evm_transfer(self, wallet: WalletInfo, to_address: str, 
                     amount: float, token: Optional[str] = None) -> str:
        """EVM 链转账"""
        if not WEB3_AVAILABLE:
            raise ImportError("web3.py 未安装")
        
        chain = wallet.chain
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(self.config[chain]['rpc']))
        if chain == "bsc":
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        if token:
            # ERC20 转账
            # TODO: 实现代币转账
            raise NotImplementedError("代币转账尚未实现")
        else:
            # 原生代币转账
            amount_wei = w3.to_wei(amount, 'ether')
            
            # 构建交易
            nonce = w3.eth.get_transaction_count(wallet.address)
            tx = {
                'nonce': nonce,
                'to': to_address,
                'value': amount_wei,
                'gas': 21000,
                'gasPrice': w3.eth.gas_price,
                'chainId': self.config[chain]['chain_id']
            }
            
            # 签名并发送
            signed = w3.eth.account.sign_transaction(tx, wallet.private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            
            return tx_hash.hex()
    
    def _solana_transfer(self, wallet: WalletInfo, to_address: str,
                        amount: float, token: Optional[str] = None) -> str:
        """Solana 转账"""
        if not SOLANA_AVAILABLE:
            raise ImportError("solana-py 未安装")
        
        # TODO: 实现 Solana 转账
        raise NotImplementedError("Solana 转账尚未实现")
    
    def get_all_balances(self) -> Dict[str, Dict]:
        """获取所有钱包余额"""
        balances = {}
        for key, wallet in self.wallets.items():
            try:
                balance = self.get_balance(wallet.chain, key.split('_', 1)[1])
                balances[key] = {
                    "chain": wallet.chain,
                    "address": wallet.address,
                    "balance": balance
                }
            except Exception as e:
                print(f"⚠️  获取 {key} 余额失败: {e}")
                balances[key] = {
                    "chain": wallet.chain,
                    "address": wallet.address,
                    "error": str(e)
                }
        return balances

# 便捷函数
def get_agent_balance(agent_name: str, chain: str = "bsc") -> float:
    """获取代理余额（兼容现有接口）"""
    wallet_manager = MultiChainWallet()
    return wallet_manager.get_balance(chain, agent_name)

def send_payment(from_agent: str, to_agent: str, amount: float, 
                chain: str = "bsc") -> str:
    """发送支付（兼容现有接口）"""
    wallet_manager = MultiChainWallet()
    
    # 获取收款人地址
    to_wallet = wallet_manager.get_wallet(chain, to_agent)
    if not to_wallet:
        raise ValueError(f"收款人钱包不存在: {chain}_{to_agent}")
    
    return wallet_manager.transfer(chain, from_agent, to_wallet.address, amount)

if __name__ == "__main__":
    # 测试钱包管理
    print("🧪 多链钱包管理器测试")
    
    wallet_manager = MultiChainWallet()
    
    print(f"📋 当前钱包数量: {len(wallet_manager.wallets)}")
    print(f"💰 所有余额: {wallet_manager.get_all_balances()}")