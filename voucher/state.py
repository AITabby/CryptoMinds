"""
Voucher 状态机

按量计费 Voucher 生命周期:
issued → active → exhausted (终态)
              → disputed → resolved_refund / resolved_release (终态)
              → cancelled (终态)
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class VoucherState(Enum):
    ISSUED = "issued"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    DISPUTED = "disputed"
    RESOLVED_REFUND = "resolved_refund"
    RESOLVED_RELEASE = "resolved_release"
    CANCELLED = "cancelled"


class InvalidTransitionError(Exception):
    pass


@dataclass
class VoucherTransition:
    action: str
    from_state: VoucherState
    to_state: VoucherState
    timestamp: int = 0
    actor: str = ""
    reason: str = ""


VALID_TRANSITIONS = {
    VoucherState.ISSUED: {
        "activate": VoucherState.ACTIVE,
        "cancel": VoucherState.CANCELLED,
    },
    VoucherState.ACTIVE: {
        "use": VoucherState.ACTIVE,          # consume units, stay active
        "exhaust": VoucherState.EXHAUSTED,   # all units consumed
        "dispute": VoucherState.DISPUTED,
        "cancel": VoucherState.CANCELLED,
    },
    VoucherState.DISPUTED: {
        "arbitrate_buyer_win": VoucherState.RESOLVED_REFUND,
        "arbitrate_seller_win": VoucherState.RESOLVED_RELEASE,
        "auto_resolve_buyer_win": VoucherState.RESOLVED_REFUND,
        "auto_resolve_seller_win": VoucherState.RESOLVED_RELEASE,
    },
}

TERMINAL_STATES = {
    VoucherState.EXHAUSTED,
    VoucherState.RESOLVED_REFUND,
    VoucherState.RESOLVED_RELEASE,
    VoucherState.CANCELLED,
}


class VoucherStateMachine:
    def __init__(self, initial_state: VoucherState = VoucherState.ISSUED):
        self._state = initial_state
        self._history: List[VoucherTransition] = []

    @property
    def state(self) -> VoucherState:
        return self._state

    def can_transition(self, action: str) -> bool:
        transitions = VALID_TRANSITIONS.get(self._state, {})
        return action in transitions

    def transition(
        self,
        action: str,
        timestamp: int = 0,
        actor: str = "",
        reason: str = "",
    ) -> VoucherState:
        transitions = VALID_TRANSITIONS.get(self._state, {})
        if action not in transitions:
            legal = list(transitions.keys())
            raise InvalidTransitionError(
                f"非法转换: {self._state.value} + {action} (合法动作: {legal})"
            )

        target = transitions[action]
        tr = VoucherTransition(
            action=action,
            from_state=self._state,
            to_state=target,
            timestamp=timestamp or int(time.time()),
            actor=actor,
            reason=reason,
        )
        self._history.append(tr)
        self._state = target
        return self._state