"""
Voucher 按量计费数据模型
"""

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from .state import VoucherState


@dataclass
class Voucher:
    voucher_id: str
    issuer_wallet: str           # buyer who prepays
    agent_id: str                # seller agent
    capability_task_type: str    # what the voucher covers (e.g. "data_delivery")
    unit_price: Decimal          # price per unit
    unit_type: str               # unit label (e.g. "api_call", "token_analysis")
    total_units: int             # how many units prepaid
    units_used: int = 0          # how many consumed so far
    total_deposit: Decimal = Decimal("0")  # total_units * unit_price
    channel_id: str = "mock"
    chain: str = "mock"
    escrow_id: Optional[str] = None       # linked escrow order for deposit
    state: VoucherState = VoucherState.ISSUED
    created_at: int = field(default_factory=lambda: int(time.time()))
    activated_at: int = 0
    exhausted_at: int = 0
    cancelled_at: int = 0
    disputed_at: int = 0
    resolved_at: int = 0
    expires_at: int = 0
    dispute_reason: str = ""
    dispute_initiator: str = ""
    resolution: str = ""
    resolution_reason: str = ""

    @property
    def units_remaining(self) -> int:
        return self.total_units - self.units_used

    @property
    def remaining_deposit(self) -> Decimal:
        return self.unit_price * self.units_remaining

    def to_dict(self) -> Dict:
        return {
            "voucher_id": self.voucher_id,
            "issuer_wallet": self.issuer_wallet,
            "agent_id": self.agent_id,
            "capability_task_type": self.capability_task_type,
            "unit_price": str(self.unit_price),
            "unit_type": self.unit_type,
            "total_units": self.total_units,
            "units_used": self.units_used,
            "units_remaining": self.units_remaining,
            "total_deposit": str(self.total_deposit),
            "remaining_deposit": str(self.remaining_deposit),
            "channel_id": self.channel_id,
            "chain": self.chain,
            "escrow_id": self.escrow_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "exhausted_at": self.exhausted_at,
            "cancelled_at": self.cancelled_at,
            "disputed_at": self.disputed_at,
            "resolved_at": self.resolved_at,
            "expires_at": self.expires_at,
            "dispute_reason": self.dispute_reason,
            "dispute_initiator": self.dispute_initiator,
            "resolution": self.resolution,
            "resolution_reason": self.resolution_reason,
        }