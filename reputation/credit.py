"""
信用货币

高信誉 Agent 可以发行信用 IOU，作为支付手段。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
import time
import hashlib


@dataclass
class CreditCurrency:
    """
    信用货币

    由高信誉 Agent 发行的 IOU（I Owe You）。
    其他 Agent 可以接受作为支付手段。
    """

    # 基本信息
    currency_id: str = ""
    issuer_agent_id: str = ""
    issuer_wallet: str = ""

    # 发行信息
    name: str = ""                  # 如 "MemeSniper Credit"
    symbol: str = ""                # 如 "MSC"
    decimals: int = 18

    # 发行量
    total_supply: Decimal = Decimal("0")
    max_supply: Decimal = Decimal("0")
    backed_by: str = ""             # 抵押物（如 "BNB", "USDC"）

    # 信誉要求
    min_reputation_score: float = 4.0   # 发行者最低信誉分
    min_stake_ratio: float = 0.5         # 最低质押率（发行量/质押量）

    # 状态
    active: bool = True
    created_at: int = field(default_factory=lambda: int(time.time()))

    # 接受度
    accepted_by: List[str] = field(default_factory=list)  # 接受此货币的 Agent 列表

    def to_dict(self) -> Dict:
        return {
            "currency_id": self.currency_id,
            "issuer_agent_id": self.issuer_agent_id,
            "issuer_wallet": self.issuer_wallet,
            "name": self.name,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "total_supply": str(self.total_supply),
            "max_supply": str(self.max_supply),
            "backed_by": self.backed_by,
            "min_reputation_score": self.min_reputation_score,
            "min_stake_ratio": self.min_stake_ratio,
            "active": self.active,
            "created_at": self.created_at,
            "accepted_by": self.accepted_by,
        }


@dataclass
class CreditBalance:
    """信用货币余额"""

    currency_id: str = ""
    wallet: str = ""
    balance: Decimal = Decimal("0")

    def to_dict(self) -> Dict:
        return {
            "currency_id": self.currency_id,
            "wallet": self.wallet,
            "balance": str(self.balance),
        }


class CreditRegistry:
    """
    信用货币注册表

    支持内存+JSON 持久化，重启后自动恢复。
    """

    _persistence_path: Optional[str] = None

    def __init__(self):
        self._currencies: Dict[str, CreditCurrency] = {}
        self._balances: Dict[str, Dict[str, Decimal]] = {}  # currency_id -> {wallet -> balance}
        self._issuer_index: Dict[str, str] = {}  # issuer_wallet -> currency_id
        self._load()

    def set_persistence(self, path: str):
        """设置持久化文件路径"""
        CreditRegistry._persistence_path = path
        self._load()

    def _save(self):
        """持久化到 JSON"""
        if not CreditRegistry._persistence_path:
            return
        try:
            import json
            data = {
                'currencies': {cid: c.to_dict() for cid, c in self._currencies.items()},
                'balances': {cid: {w: str(b) for w, b in bals.items()} for cid, bals in self._balances.items()},
                'issuer_index': self._issuer_index,
            }
            with open(CreditRegistry._persistence_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[CreditRegistry] 持久化失败: {e}")

    def _load(self):
        """从 JSON 恢复"""
        if not CreditRegistry._persistence_path:
            return
        try:
            import json, os
            if not os.path.exists(CreditRegistry._persistence_path):
                return
            with open(CreditRegistry._persistence_path, 'r') as f:
                data = json.load(f)
            for cid, c_dict in data.get('currencies', {}).items():
                self._currencies[cid] = CreditCurrency(**{k: (Decimal(str(v)) if k in ('total_supply', 'max_supply') else v) for k, v in c_dict.items() if k != 'accepted_by'})
                if 'accepted_by' in c_dict:
                    self._currencies[cid].accepted_by = c_dict['accepted_by']
            for cid, bals in data.get('balances', {}).items():
                self._balances[cid] = {w: Decimal(b) for w, b in bals.items()}
            self._issuer_index = data.get('issuer_index', {})
            print(f"[CreditRegistry] 从 {CreditRegistry._persistence_path} 恢复 {len(self._currencies)} 个信用货币")
        except Exception as e:
            print(f"[CreditRegistry] 恢复失败: {e}")

    # ── 发行 ─────────────────────────────────────────

    def issue(
        self,
        issuer_agent_id: str,
        issuer_wallet: str,
        name: str,
        symbol: str,
        max_supply: Decimal,
        backed_by: str = "",
        min_reputation_score: float = 4.0,
    ) -> Dict:
        """
        发行信用货币

        Args:
            issuer_agent_id: 发行者 Agent ID
            issuer_wallet: 发行者钱包
            name: 货币名称
            symbol: 货币符号
            max_supply: 最大发行量
            backed_by: 抵押物
            min_reputation_score: 最低信誉分要求

        Returns:
            发行结果
        """
        # 检查是否已发行
        if issuer_wallet in self._issuer_index:
            return {"error": "该钱包已发行信用货币"}

        # 生成货币 ID
        currency_id = hashlib.sha256(
            f"{issuer_wallet}{symbol}{time.time()}".encode()
        ).hexdigest()[:16]

        # 创建货币
        currency = CreditCurrency(
            currency_id=currency_id,
            issuer_agent_id=issuer_agent_id,
            issuer_wallet=issuer_wallet,
            name=name,
            symbol=symbol,
            max_supply=max_supply,
            backed_by=backed_by,
            min_reputation_score=min_reputation_score,
        )

        self._currencies[currency_id] = currency
        self._issuer_index[issuer_wallet] = currency_id
        self._balances[currency_id] = {issuer_wallet: max_supply}  # 初始发行给发行者

        self._save()
        return {
            "ok": True,
            "currency_id": currency_id,
            "message": f"信用货币 {symbol} 发行成功",
        }

    # ── 转账 ─────────────────────────────────────────

    def transfer(
        self,
        currency_id: str,
        from_wallet: str,
        to_wallet: str,
        amount: Decimal,
    ) -> Dict:
        """
        转账信用货币

        Args:
            currency_id: 货币 ID
            from_wallet: 发送方钱包
            to_wallet: 接收方钱包
            amount: 数量

        Returns:
            转账结果
        """
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}

        if not currency.active:
            return {"error": "货币已停用"}

        balances = self._balances.get(currency_id, {})
        from_balance = balances.get(from_wallet, Decimal("0"))

        if from_balance < amount:
            return {"error": "余额不足"}

        # 执行转账
        balances[from_wallet] = from_balance - amount
        balances[to_wallet] = balances.get(to_wallet, Decimal("0")) + amount

        self._save()
        return {
            "ok": True,
            "from_balance": str(balances[from_wallet]),
            "to_balance": str(balances[to_wallet]),
        }

    # ── 查询 ─────────────────────────────────────────

    def get_currency(self, currency_id: str) -> Optional[CreditCurrency]:
        """获取货币信息"""
        return self._currencies.get(currency_id)

    def get_by_issuer(self, issuer_wallet: str) -> Optional[CreditCurrency]:
        """通过发行者获取货币"""
        currency_id = self._issuer_index.get(issuer_wallet)
        if currency_id:
            return self._currencies.get(currency_id)
        return None

    def get_balance(self, currency_id: str, wallet: str) -> Decimal:
        """查询余额"""
        balances = self._balances.get(currency_id, {})
        return balances.get(wallet, Decimal("0"))

    def list_all(self) -> List[Dict]:
        """列出所有货币"""
        return [c.to_dict() for c in self._currencies.values()]

    def list_accepted_by(self, agent_id: str) -> List[CreditCurrency]:
        """列出某 Agent 接受的所有货币"""
        return [
            c for c in self._currencies.values()
            if agent_id in c.accepted_by
        ]

    # ── 接受/拒绝 ────────────────────────────────────

    def accept_currency(self, currency_id: str, agent_id: str) -> bool:
        """Agent 接受某货币作为支付手段"""
        currency = self._currencies.get(currency_id)
        if not currency:
            return False

        if agent_id not in currency.accepted_by:
            currency.accepted_by.append(agent_id)

        self._save()
        return True

    def reject_currency(self, currency_id: str, agent_id: str) -> bool:
        """Agent 拒绝某货币"""
        currency = self._currencies.get(currency_id)
        if not currency:
            return False

        if agent_id in currency.accepted_by:
            currency.accepted_by.remove(agent_id)

        self._save()
        return True

    # ── 信用货币支付 ──────────────────────────────────

    def pay_with_credit(
        self,
        currency_id: str,
        from_wallet: str,
        to_wallet: str,
        amount: Decimal,
        to_agent_id: str = None,
    ) -> Dict:
        """
        用信用货币支付

        Args:
            currency_id: 货币 ID
            from_wallet: 发送方钱包
            to_wallet: 接收方钱包
            amount: 数量
            to_agent_id: 接收方 Agent ID（用于检查接受度）

        Returns:
            支付结果
        """
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}

        if not currency.active:
            return {"error": "货币已停用"}

        # 检查接受度
        if to_agent_id and to_agent_id not in currency.accepted_by:
            return {"error": f"Agent {to_agent_id} 不接受此货币"}

        # 检查余额
        balances = self._balances.get(currency_id, {})
        from_balance = balances.get(from_wallet, Decimal("0"))

        if from_balance < amount:
            return {"error": f"余额不足: {from_balance} < {amount}"}

        # 执行转账
        balances[from_wallet] = from_balance - amount
        balances[to_wallet] = balances.get(to_wallet, Decimal("0")) + amount

        self._save()

        # 记录交易
        import hashlib
        import time
        tx_hash = hashlib.sha256(
            f"{currency_id}{from_wallet}{to_wallet}{amount}{time.time()}".encode()
        ).hexdigest()[:32]

        return {
            "ok": True,
            "tx_hash": tx_hash,
            "currency_id": currency_id,
            "symbol": currency.symbol,
            "from_balance": str(balances[from_wallet]),
            "to_balance": str(balances[to_wallet]),
            "amount": str(amount),
        }

    def check_acceptance(
        self,
        currency_id: str,
        agent_id: str,
    ) -> Dict:
        """
        检查 Agent 是否接受某货币

        Returns:
            接受状态和信任分
        """
        currency = self._currencies.get(currency_id)
        if not currency:
            return {"error": f"未知货币: {currency_id}"}

        accepted = agent_id in currency.accepted_by
        trust_score = self.get_trust_score(currency_id)

        return {
            "currency_id": currency_id,
            "symbol": currency.symbol,
            "issuer_agent_id": currency.issuer_agent_id,
            "accepted": accepted,
            "trust_score": trust_score,
            "min_reputation_score": currency.min_reputation_score,
        }

    def get_acceptable_currencies(
        self,
        agent_id: str,
        min_trust_score: float = 0.5,
    ) -> List[Dict]:
        """
        获取 Agent 可接受的货币列表

        返回信任分 >= min_trust_score 的货币
        """
        result = []
        for currency in self._currencies.values():
            if not currency.active:
                continue

            trust_score = self.get_trust_score(currency.currency_id)
            if trust_score >= min_trust_score:
                accepted = agent_id in currency.accepted_by
                result.append({
                    "currency_id": currency.currency_id,
                    "symbol": currency.symbol,
                    "name": currency.name,
                    "issuer_agent_id": currency.issuer_agent_id,
                    "trust_score": trust_score,
                    "accepted": accepted,
                })

        return result

    # ── 验证 ─────────────────────────────────────────

    def verify_payment_capability(
        self,
        currency_id: str,
        wallet: str,
        amount: Decimal,
    ) -> bool:
        """
        验证支付能力

        检查钱包是否有足够的信用货币余额。
        """
        balance = self.get_balance(currency_id, wallet)
        return balance >= amount

    def get_trust_score(self, currency_id: str) -> float:
        """
        获取货币信任分

        基于发行者信誉和接受度计算。
        """
        currency = self._currencies.get(currency_id)
        if not currency:
            return 0.0

        # 接受度得分
        acceptance_score = min(1.0, len(currency.accepted_by) / 10)

        # 质押率得分（需要外部数据）
        # 这里简化处理

        return acceptance_score * 0.5 + currency.min_reputation_score / 5.0 * 0.5

    # ── 清理 ─────────────────────────────────────────

    def clear(self):
        """清空所有数据（测试用）"""
        self._currencies.clear()
        self._balances.clear()
        self._issuer_index.clear()
        self._save()
