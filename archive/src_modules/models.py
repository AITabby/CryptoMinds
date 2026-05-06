"""
Escrow 数据模型

EscrowOrder dataclass — 托管订单的完整生命周期数据。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from settlement.escrow_state import EscrowState, EscrowTransition


@dataclass
class EscrowOrder:
    escrow_id: str
    task_id: str
    order_id: str                     # Node.js order ID

    # Parties
    buyer_wallet: str
    seller_wallet: str
    seller_agent_id: str

    # Financial
    amount: Decimal
    channel_id: str
    chain: str = "bsc"
    on_chain_order_id: Optional[str] = None  # bytes32 from ServiceEscrow.sol
    chain_synced: bool = True  # False if DB state changed but on-chain state not yet updated

    # State machine
    state: EscrowState = EscrowState.CREATED
    state_history: List[EscrowTransition] = field(default_factory=list)

    # Timestamps
    created_at: int = 0
    funded_at: int = 0
    delivered_at: int = 0
    verified_at: int = 0
    disputed_at: int = 0
    resolved_at: int = 0
    seller_timeout_at: int = 0
    buyer_timeout_at: int = 0

    # Dispute
    dispute_reason: str = ""
    dispute_initiator: str = ""       # buyer / seller / system
    arbitration_weight_buyer: float = 0.0
    arbitration_weight_seller: float = 0.0
    resolution: str = ""              # buyer_win / seller_win / split
    resolution_reason: str = ""

    # Verification
    verification_score: float = 0.0
    verification_evidence: Dict = field(default_factory=dict)
    verification_threshold: float = 0.7  # below this → dispute

    # Dispute window
    dispute_window_seconds: int = 172800  # 48 hours default

    def to_dict(self) -> Dict:
        return {
            "escrow_id": self.escrow_id,
            "task_id": self.task_id,
            "order_id": self.order_id,
            "buyer_wallet": self.buyer_wallet,
            "seller_wallet": self.seller_wallet,
            "seller_agent_id": self.seller_agent_id,
            "amount": str(self.amount),
            "channel_id": self.channel_id,
            "chain": self.chain,
            "on_chain_order_id": self.on_chain_order_id,
            "chain_synced": self.chain_synced,
            "state": self.state.value,
            "created_at": self.created_at,
            "funded_at": self.funded_at,
            "delivered_at": self.delivered_at,
            "verified_at": self.verified_at,
            "disputed_at": self.disputed_at,
            "resolved_at": self.resolved_at,
            "seller_timeout_at": self.seller_timeout_at,
            "buyer_timeout_at": self.buyer_timeout_at,
            "dispute_reason": self.dispute_reason,
            "dispute_initiator": self.dispute_initiator,
            "arbitration_weight_buyer": self.arbitration_weight_buyer,
            "arbitration_weight_seller": self.arbitration_weight_seller,
            "resolution": self.resolution,
            "resolution_reason": self.resolution_reason,
            "verification_score": self.verification_score,
            "verification_threshold": self.verification_threshold,
            "dispute_window_seconds": self.dispute_window_seconds,
        }