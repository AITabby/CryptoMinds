"""
Agent 注册表

管理所有注册的 Agent，支持语义匹配和查询。
"""

from typing import Dict, List, Optional
from decimal import Decimal
import time

from .capability import AgentCapability, CapabilitySpec


class AgentRegistry:
    """
    Agent 注册表

    支持内存+JSON 持久化，重启后自动恢复。
    """

    _agents: Dict[str, AgentCapability] = {}
    _wallet_index: Dict[str, str] = {}  # wallet -> agent_id
    _persistence_path: Optional[str] = None  # JSON 持久化路径
    _sqlite_bridge: Optional[object] = None  # SqliteAgentBridge instance

    @classmethod
    def set_persistence(cls, path: str):
        """设置持久化文件路径"""
        cls._persistence_path = path
        cls._load()

    @classmethod
    def set_sqlite_bridge(cls, bridge):
        """设置 SQLite bridge，注册/注销时同步到 SQLite"""
        cls._sqlite_bridge = bridge

    @classmethod
    def _save(cls):
        """持久化到 JSON"""
        if not cls._persistence_path:
            return
        try:
            import json
            data = {aid: a.to_dict() for aid, a in cls._agents.items()}
            with open(cls._persistence_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[AgentRegistry] 持久化失败: {e}")

    @classmethod
    def _load(cls):
        """从 JSON 恢复"""
        if not cls._persistence_path:
            return
        try:
            import json
            import os
            if not os.path.exists(cls._persistence_path):
                return
            with open(cls._persistence_path, 'r') as f:
                data = json.load(f)
            for aid, agent_dict in data.items():
                agent = AgentCapability.from_dict(agent_dict)
                cls._agents[aid] = agent
                if agent.wallet:
                    cls._wallet_index[agent.wallet.lower()] = aid
            print(f"[AgentRegistry] 从 {cls._persistence_path} 恢复 {len(cls._agents)} 个 Agent")
        except Exception as e:
            print(f"[AgentRegistry] 恢复失败: {e}")

    # ── 注册/注销 ─────────────────────────────────────

    @classmethod
    def register(cls, agent: AgentCapability) -> None:
        """注册 Agent"""
        if not agent.agent_id:
            raise ValueError("Agent 必须定义 agent_id")

        cls._agents[agent.agent_id] = agent

        # 建立钱包索引
        if agent.wallet:
            cls._wallet_index[agent.wallet.lower()] = agent.agent_id

        cls._save()
        if cls._sqlite_bridge:
            cls._sqlite_bridge.save_agent(agent)

    @classmethod
    def unregister(cls, agent_id: str) -> bool:
        """注销 Agent"""
        if agent_id in cls._agents:
            agent = cls._agents[agent_id]
            # 清除钱包索引
            if agent.wallet and agent.wallet.lower() in cls._wallet_index:
                del cls._wallet_index[agent.wallet.lower()]
            del cls._agents[agent_id]
            cls._save()
            if cls._sqlite_bridge:
                cls._sqlite_bridge.remove_agent(agent_id, agent.wallet or "")
            return True
        return False

    @classmethod
    def update(cls, agent_id: str, **kwargs) -> Optional[AgentCapability]:
        """更新 Agent 信息"""
        agent = cls._agents.get(agent_id)
        if not agent:
            return None

        for key, value in kwargs.items():
            if hasattr(agent, key):
                setattr(agent, key, value)

        agent.updated_at = int(time.time())
        cls._save()
        return agent

    # ── 查询 ─────────────────────────────────────────

    @classmethod
    def get(cls, agent_id: str) -> Optional[AgentCapability]:
        """获取指定 Agent"""
        return cls._agents.get(agent_id)

    @classmethod
    def get_by_wallet(cls, wallet: str) -> Optional[AgentCapability]:
        """通过钱包地址获取 Agent"""
        agent_id = cls._wallet_index.get(wallet.lower())
        if agent_id:
            return cls._agents.get(agent_id)
        return None

    @classmethod
    def list_all(cls) -> List[AgentCapability]:
        """列出所有 Agent"""
        return list(cls._agents.values())

    @classmethod
    def list_online(cls) -> List[AgentCapability]:
        """列出所有在线 Agent"""
        return [a for a in cls._agents.values() if a.online]

    # ── 搜索与匹配 ───────────────────────────────────

    @classmethod
    def search(
        cls,
        task_type: str = None,
        chain: str = None,
        amount: Decimal = None,
        min_reputation: float = None,
        online_only: bool = True,
        sort_by: str = "reputation",  # reputation, price, volume
        limit: int = 10,
    ) -> List[AgentCapability]:
        """
        搜索匹配的 Agent

        Args:
            task_type: 任务类型
            chain: 链
            amount: 金额
            min_reputation: 最低信誉分
            online_only: 只返回在线 Agent
            sort_by: 排序方式
            limit: 返回数量

        Returns:
            匹配的 Agent 列表
        """
        results = []

        for agent in cls._agents.values():
            # 过滤：在线
            if online_only and not agent.online:
                continue

            # 过滤：信誉
            if min_reputation and agent.reputation.score < min_reputation:
                continue

            # 过滤：任务类型
            if task_type:
                cap = agent.get_capability(task_type)
                if not cap:
                    continue

                # 过滤：链
                if chain and chain not in cap.supported_chains:
                    continue

                # 过滤：金额
                if amount and not agent.can_accept(task_type, chain or "", amount):
                    continue

            results.append(agent)

        # 排序
        if sort_by == "reputation":
            results.sort(key=lambda a: a.reputation.score, reverse=True)
        elif sort_by == "price":
            # 按价格升序（需要 task_type）
            if task_type:
                results.sort(key=lambda a: a.get_price(task_type, amount or Decimal("0")))
        elif sort_by == "volume":
            results.sort(key=lambda a: a.reputation.total_volume, reverse=True)
        elif sort_by == "success_rate":
            results.sort(key=lambda a: a.reputation.success_rate, reverse=True)

        return results[:limit]

    @classmethod
    def find_best_match(
        cls,
        task_type: str,
        chain: str,
        amount: Decimal,
        strategy: str = "balanced",  # reputation, price, balanced
    ) -> Optional[AgentCapability]:
        """
        找到最佳匹配的 Agent

        Args:
            task_type: 任务类型
            chain: 链
            amount: 金额
            strategy: 选择策略

        Returns:
            最佳匹配的 Agent
        """
        agents = cls.search(
            task_type=task_type,
            chain=chain,
            amount=amount,
            online_only=True,
            limit=20,
        )

        if not agents:
            return None

        if strategy == "reputation":
            return max(agents, key=lambda a: a.reputation.score)

        if strategy == "price":
            return min(agents, key=lambda a: a.get_price(task_type, amount))

        # balanced: 综合评分
        def balanced_score(agent: AgentCapability) -> float:
            rep_score = agent.reputation.score / 5.0  # 0-1
            success_score = agent.reputation.success_rate  # 0-1
            volume_score = min(1.0, float(agent.reputation.total_volume) / 100)  # 归一化

            # 权重: 信誉 40%, 成功率 40%, 交易量 20%
            return rep_score * 0.4 + success_score * 0.4 + volume_score * 0.2

        return max(agents, key=balanced_score)

    # ── 统计 ─────────────────────────────────────────

    @classmethod
    def count(cls) -> int:
        """Agent 总数"""
        return len(cls._agents)

    @classmethod
    def count_online(cls) -> int:
        """在线 Agent 数"""
        return len([a for a in cls._agents.values() if a.online])

    @classmethod
    def get_stats(cls) -> Dict:
        """获取统计信息"""
        agents = list(cls._agents.values())

        if not agents:
            return {
                "total": 0,
                "online": 0,
                "avg_reputation": 0,
                "total_volume": "0",
            }

        return {
            "total": len(agents),
            "online": len([a for a in agents if a.online]),
            "avg_reputation": sum(a.reputation.score for a in agents) / len(agents),
            "total_volume": str(sum(a.reputation.total_volume for a in agents)),
        }

    # ── 管理 ─────────────────────────────────────────

    @classmethod
    def clear(cls) -> None:
        """清空所有注册（测试用）"""
        cls._agents.clear()
        cls._wallet_index.clear()
        cls._save()


# 导入 Dict 类型
from typing import Dict