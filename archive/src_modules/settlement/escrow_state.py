"""
Escrow 状态机

定义 EscrowState enum 和合法转换规则。
映射到链上 ServiceEscrow.OrderStatus 和 Node.js ORDER_STATUS。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class EscrowState(Enum):
    CREATED = "created"           # 初始状态, 等待买家锁资金
    FUNDED = "funded"             # 买家已锁资金, 等待卖家接受
    EXECUTING = "executing"       # 卖家已接受, 正在执行
    DELIVERED = "delivered"       # 卖家已提交结果
    VERIFIED = "verified"         # 验证门通过 (off-chain only)
    DISPUTED = "disputed"         # 进入争议窗口
    RELEASED = "released"         # 资金已释放给卖家 (终态)
    RESOLVED_REFUND = "resolved_refund"   # 仲裁退款给买家 (终态)
    RESOLVED_RELEASE = "resolved_release" # 仲裁释放给卖家 (终态)
    EXPIRED = "expired"           # 买家验收超时, 自动释放 (终态)
    REFUNDED_TIMEOUT = "refunded_timeout" # 卖家超时, 退款 (终态)

    @classmethod
    def from_chain_status(cls, chain_status: int) -> "EscrowState":
        """映射链上 ServiceEscrow.OrderStatus"""
        mapping = {
            0: cls.CREATED,     # None
            1: cls.FUNDED,      # Pending
            2: cls.EXECUTING,   # Delivering
            3: cls.DELIVERED,   # Delivered
            4: cls.RELEASED,    # Confirmed
            5: cls.DISPUTED,    # Disputed
            6: cls.RESOLVED_REFUND,  # Refunded
            7: cls.EXPIRED,     # Expired
        }
        return mapping.get(chain_status, cls.CREATED)

    def to_chain_status(self) -> int:
        """映射到链上 OrderStatus"""
        mapping = {
            EscrowState.CREATED: 0,
            EscrowState.FUNDED: 1,
            EscrowState.EXECUTING: 2,
            EscrowState.DELIVERED: 3,
            EscrowState.RELEASED: 4,
            EscrowState.DISPUTED: 5,
            EscrowState.RESOLVED_REFUND: 6,
            EscrowState.EXPIRED: 7,
            # off-chain states map to nearest on-chain equivalent
            EscrowState.VERIFIED: 3,  # still Delivered on chain
            EscrowState.RESOLVED_RELEASE: 4,  # becomes Confirmed on chain
            EscrowState.REFUNDED_TIMEOUT: 6,  # becomes Refunded on chain
        }
        return mapping.get(self, 0)

    @property
    def is_terminal(self) -> bool:
        return self in (
            EscrowState.RELEASED,
            EscrowState.RESOLVED_REFUND,
            EscrowState.RESOLVED_RELEASE,
            EscrowState.EXPIRED,
            EscrowState.REFUNDED_TIMEOUT,
        )


@dataclass
class EscrowTransition:
    action: str
    from_state: EscrowState
    to_state: EscrowState
    timestamp: int = 0
    actor: str = ""        # buyer / seller / system / admin
    reason: str = ""


class InvalidTransitionError(Exception):
    pass


# 合法转换表: {from_state: {action: to_state}}
VALID_TRANSITIONS: Dict[EscrowState, Dict[str, EscrowState]] = {
    EscrowState.CREATED: {
        "fund": EscrowState.FUNDED,
    },
    EscrowState.FUNDED: {
        "seller_accept": EscrowState.EXECUTING,
        "seller_timeout": EscrowState.REFUNDED_TIMEOUT,
    },
    EscrowState.EXECUTING: {
        "deliver": EscrowState.DELIVERED,
        "seller_timeout": EscrowState.REFUNDED_TIMEOUT,
    },
    EscrowState.DELIVERED: {
        "verify_pass": EscrowState.VERIFIED,
        "verify_fail": EscrowState.DISPUTED,
        "verify_low_score": EscrowState.DISPUTED,
        "buyer_timeout": EscrowState.EXPIRED,
        "dispute": EscrowState.DISPUTED,
    },
    EscrowState.VERIFIED: {
        "release": EscrowState.RELEASED,
    },
    EscrowState.DISPUTED: {
        "arbitrate_buyer_win": EscrowState.RESOLVED_REFUND,
        "arbitrate_seller_win": EscrowState.RESOLVED_RELEASE,
        "arbitrate_split": EscrowState.RESOLVED_RELEASE,
        "auto_resolve_buyer_win": EscrowState.RESOLVED_REFUND,
        "auto_resolve_seller_win": EscrowState.RESOLVED_RELEASE,
        "auto_resolve_split": EscrowState.RESOLVED_RELEASE,
    },
}


class EscrowStateMachine:
    """Escrow 状态机: 验证转换合法性, 记录历史"""

    def __init__(self, initial_state: EscrowState = EscrowState.CREATED):
        self._state = initial_state
        self._history: List[EscrowTransition] = []

    @property
    def state(self) -> EscrowState:
        return self._state

    @property
    def history(self) -> List[EscrowTransition]:
        return list(self._history)

    def can_transition(self, action: str) -> bool:
        transitions = VALID_TRANSITIONS.get(self._state, {})
        return action in transitions

    def transition(self, action: str, timestamp: int = 0,
                   actor: str = "", reason: str = "") -> EscrowState:
        transitions = VALID_TRANSITIONS.get(self._state, {})
        if action not in transitions:
            raise InvalidTransitionError(
                f"非法转换: {self._state.value} + {action} "
                f"(合法动作: {list(transitions.keys())})"
            )

        new_state = transitions[action]
        record = EscrowTransition(
            action=action,
            from_state=self._state,
            to_state=new_state,
            timestamp=timestamp,
            actor=actor,
            reason=reason,
        )
        self._history.append(record)
        self._state = new_state
        return new_state

    def get_timestamp_for_state(self, target_state: EscrowState) -> Optional[int]:
        for t in self._history:
            if t.to_state == target_state:
                return t.timestamp
        return None
