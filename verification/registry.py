"""
验证门注册表

管理所有可用的验证门，支持动态注册和查询。
"""

from typing import Dict, List, Optional
from .base import VerificationGate


class GateRegistry:
    """
    验证门注册表

    用法:
        # 注册验证门
        GateRegistry.register(TokenDeliveryGate())
        GateRegistry.register(DataDeliveryGate())

        # 获取验证门
        gate = GateRegistry.get("token_delivery")

        # 列出所有验证门
        all_gates = GateRegistry.list_all()
    """

    _gates: Dict[str, VerificationGate] = {}

    @classmethod
    def register(cls, gate: VerificationGate) -> None:
        """注册验证门"""
        if not gate.gate_id:
            raise ValueError("验证门必须定义 gate_id")
        cls._gates[gate.gate_id] = gate

    @classmethod
    def unregister(cls, gate_id: str) -> bool:
        """注销验证门"""
        if gate_id in cls._gates:
            del cls._gates[gate_id]
            return True
        return False

    @classmethod
    def get(cls, gate_id: str) -> Optional[VerificationGate]:
        """获取指定验证门"""
        return cls._gates.get(gate_id)

    @classmethod
    def get_for_task_type(cls, task_type: str) -> List[VerificationGate]:
        """获取指定任务类型的所有验证门"""
        return [g for g in cls._gates.values() if g.task_type == task_type]

    @classmethod
    def get_for_chain(cls, chain: str) -> List[VerificationGate]:
        """获取支持指定链的所有验证门"""
        return [g for g in cls._gates.values() if g.supports_chain(chain)]

    @classmethod
    def list_all(cls) -> List[Dict]:
        """列出所有验证门信息"""
        return [g.to_dict() for g in cls._gates.values()]

    @classmethod
    def list_task_types(cls) -> List[str]:
        """列出所有任务类型"""
        return list(set(g.task_type for g in cls._gates.values()))

    @classmethod
    def clear(cls) -> None:
        """清空所有注册（测试用）"""
        cls._gates.clear()


# 导入 Dict 类型
from typing import Dict