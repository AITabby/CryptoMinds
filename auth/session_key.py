"""
SessionKey 数据模型

主钱包授权: agent_id, 可用链, 单笔上限, 总额度, 有效期, 可调用动作, 可撤销 nonce。
Agent 只拿 session key 干活，主钱包保留撤销和提额权力。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List


@dataclass
class SessionKey:
    session_key_id: str               # unique identifier
    main_wallet: str                   # the wallet that authorized this session key
    agent_id: str                      # the agent that holds this session key

    # Permissions
    available_chains: List[str]        # chains this key can operate on
    per_tx_limit: Decimal              # maximum amount per single transaction
    total_quota: Decimal               # total spending quota
    total_used: Decimal                # total amount already spent (monotonically increasing)
    callable_actions: List[str]        # ["pay", "escrow", "deliver"]

    # Validity
    created_at: int
    expires_at: int                    # expiration timestamp
    nonce: int                         # revocation nonce (incremented on revoke)
    revoked: bool = False
    revoked_at: int = 0

    # Signing
    session_private_key: str = ""      # derived key (local only, never stored on-chain)
    session_address: str = ""          # derived address

    # Authorization
    authorization_signature: str = ""  # main wallet's ECDSA signature over the auth message

    def to_dict(self, include_private: bool = False) -> Dict:
        d = {
            "session_key_id": self.session_key_id,
            "main_wallet": self.main_wallet,
            "agent_id": self.agent_id,
            "available_chains": self.available_chains,
            "per_tx_limit": str(self.per_tx_limit),
            "total_quota": str(self.total_quota),
            "total_used": str(self.total_used),
            "callable_actions": self.callable_actions,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "revoked": self.revoked,
            "session_address": self.session_address,
        }
        if include_private:
            d["session_private_key"] = self.session_private_key
            d["authorization_signature"] = self.authorization_signature
        return d

    def is_valid(self, now: int = 0) -> bool:
        """Check if session key is still usable (not revoked, not expired)."""
        import time
        if now == 0:
            now = int(time.time())
        return not self.revoked and now < self.expires_at

    def can_spend(self, amount: Decimal, chain: str, action: str) -> bool:
        """Check if a specific operation is within session key permissions."""
        if chain not in self.available_chains:
            return False
        if action not in self.callable_actions:
            return False
        if amount > self.per_tx_limit:
            return False
        if self.total_used + amount > self.total_quota:
            return False
        return True

    def authorization_message(self) -> str:
        """The canonical message that the main wallet signed to authorize this session key."""
        return (
            f"CryptoMinds session key authorization\n"
            f"Agent: {self.agent_id}\n"
            f"Chains: {','.join(self.available_chains)}\n"
            f"PerTxLimit: {self.per_tx_limit}\n"
            f"TotalQuota: {self.total_quota}\n"
            f"Actions: {','.join(self.callable_actions)}\n"
            f"Nonce: {self.nonce}\n"
            f"Expires: {self.expires_at}\n"
            f"SessionAddress: {self.session_address}"
        )