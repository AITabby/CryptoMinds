"""
Session Key 签名和验证

SessionSigner: 创建 session key, 验证授权, 用 session key 签名支付请求。
"""

import hashlib
import json
import time
from decimal import Decimal
from typing import Dict, Optional

from auth.session_key import SessionKey


class SessionKeyError(Exception):
    pass


class SessionSigner:
    """Session key 创建、验证、签名"""

    def __init__(self, session_key_store=None):
        self._store = session_key_store

    def create_session_key(
        self,
        main_wallet: str,
        main_private_key: str,
        agent_id: str,
        chains: list,
        per_tx_limit: Decimal,
        total_quota: Decimal,
        actions: list,
        validity_seconds: int = 86400,
    ) -> SessionKey:
        """
        创建 session key

        1. 派生 ECDSA 密钥对
        2. 主钱包签名授权消息
        3. 存储 SessionKey
        """
        # 派生密钥对
        session_private_key, session_address = self._derive_key_pair(
            main_wallet, agent_id, main_private_key
        )

        now = int(time.time())
        expires_at = now + validity_seconds

        # 计算 session_key_id
        sk_id = hashlib.sha256(
            f"{main_wallet}:{agent_id}:{session_address}:{now}".encode()
        ).hexdigest()[:16]

        session_key = SessionKey(
            session_key_id=sk_id,
            main_wallet=main_wallet,
            agent_id=agent_id,
            available_chains=chains,
            per_tx_limit=per_tx_limit,
            total_quota=total_quota,
            total_used=Decimal("0"),
            callable_actions=actions,
            created_at=now,
            expires_at=expires_at,
            nonce=0,
            session_private_key=session_private_key,
            session_address=session_address,
        )

        # 主钱包签名授权
        auth_message = session_key.authorization_message()
        session_key.authorization_signature = self._sign_with_main_wallet(
            auth_message, main_private_key
        )

        # 存储
        if self._store:
            self._store.save(session_key)

        return session_key

    def verify_session_authorization(self, session_key: SessionKey) -> bool:
        """
        验证 session key 的授权签名

        1. 恢复签名者地址
        2. 确认签名者 == main_wallet
        3. 确认 nonce 未被撤销
        4. 确认未过期
        """
        # 恢复签名者
        recovered_address = self._recover_signer(
            session_key.authorization_message(),
            session_key.authorization_signature,
        )

        # 验证签名者
        if recovered_address.lower() != session_key.main_wallet.lower():
            return False

        # 验证 nonce (如果 store 可用，检查最新 nonce)
        if self._store:
            stored_key = self._store.get(session_key.session_key_id)
            if stored_key and stored_key.nonce != session_key.nonce:
                return False
            if stored_key and stored_key.revoked:
                return False

        # 验证过期
        if not session_key.is_valid():
            return False

        return True

    def sign_with_session_key(
        self,
        session_key: SessionKey,
        payment_request: Dict,
    ) -> Dict:
        """
        用 session key 签名支付请求

        验证权限后签名，更新 total_used。

        Returns:
            签名结果 dict (包含 signature, session_key_id, session_address)
        """
        now = int(time.time())

        # 验证 session key 状态
        if session_key.revoked:
            raise SessionKeyError("Session key 已被撤销")

        if now >= session_key.expires_at:
            raise SessionKeyError("Session key 已过期")

        # 验证授权签名
        if not self.verify_session_authorization(session_key):
            raise SessionKeyError("Session key 授权验证失败")

        # 验证权限
        chain = payment_request.get("chain", "")
        action = payment_request.get("action", "pay")
        amount = Decimal(str(payment_request.get("amount", "0")))

        if not session_key.can_spend(amount, chain, action):
            raise SessionKeyError(
                f"Session key 权限不足: chain={chain}, action={action}, amount={amount}"
            )

        # 签名
        message = json.dumps(payment_request, sort_keys=True, ensure_ascii=False)
        signature = self._sign_with_session_private_key(message, session_key.session_private_key)

        # 更新使用量
        session_key.total_used += amount
        if self._store:
            self._store.update_usage(session_key.session_key_id, amount)

        return {
            "signature": signature,
            "session_key_id": session_key.session_key_id,
            "session_address": session_key.session_address,
        }

    def revoke_session_key(self, session_key_id: str, main_wallet: str,
                           main_private_key: str) -> Dict:
        """撤销 session key (需主钱包签名确认)"""
        if not self._store:
            return {"error": "Session key store 不可用"}

        session_key = self._store.get(session_key_id)
        if not session_key:
            return {"error": f"未知 session key: {session_key_id}"}

        # 验证撤销者是主钱包
        revoke_message = f"CryptoMinds revoke session key\nKey: {session_key_id}\nWallet: {main_wallet}"
        revoke_signature = self._sign_with_main_wallet(revoke_message, main_private_key)
        recovered = self._recover_signer(revoke_message, revoke_signature)
        if recovered.lower() != session_key.main_wallet.lower():
            return {"error": "只有主钱包可以撤销 session key"}

        # 撤销
        session_key.nonce += 1
        session_key.revoked = True
        session_key.revoked_at = int(time.time())
        self._store.save(session_key)

        return {"ok": True, "nonce": session_key.nonce}

    def increase_quota(self, session_key_id: str, additional_quota: Decimal,
                       main_wallet: str, main_private_key: str) -> Dict:
        """增加 session key 总额度 (需主钱包签名确认)"""
        if not self._store:
            return {"error": "Session key store 不可用"}

        session_key = self._store.get(session_key_id)
        if not session_key:
            return {"error": f"未知 session key: {session_key_id}"}

        # 验证提额者是主钱包
        quota_message = (
            f"CryptoMinds increase session key quota\n"
            f"Key: {session_key_id}\n"
            f"Additional: {additional_quota}\n"
            f"Wallet: {main_wallet}"
        )
        quota_signature = self._sign_with_main_wallet(quota_message, main_private_key)
        recovered = self._recover_signer(quota_message, quota_signature)
        if recovered.lower() != session_key.main_wallet.lower():
            return {"error": "只有主钱包可以提额"}

        # 提额
        session_key.total_quota += additional_quota
        self._store.save(session_key)

        return {"ok": True, "total_quota": str(session_key.total_quota)}

    # ── 密钥派生 ────────────────────────────────────────

    def _derive_key_pair(self, main_wallet: str, agent_id: str,
                         main_private_key: str) -> tuple:
        """派生 ECDSA 密钥对"""
        try:
            from eth_account import Account
            # 派生: 用主私钥 + agent_id 作为种子
            seed = hashlib.sha256(
                f"{main_private_key}:{agent_id}:{main_wallet}".encode()
            ).hexdigest()
            acct = Account.create(seed)
            return acct.key.hex(), acct.address
        except ImportError:
            # Fallback: HMAC-based derivation (no eth_account)
            import hmac
            seed = hmac.new(
                main_private_key.encode(),
                f"{agent_id}:{main_wallet}".encode(),
                hashlib.sha256,
            ).hexdigest()
            return seed, f"0x{seed[:40]}"

    def _sign_with_main_wallet(self, message: str, private_key: str) -> str:
        """主钱包 ECDSA 签名"""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
            msg = encode_defunct(text=message)
            signed = Account.sign_message(msg, private_key=private_key)
            return signed.signature.hex()
        except ImportError:
            # HMAC fallback
            import hmac
            return hmac.new(
                private_key.encode(),
                message.encode(),
                hashlib.sha256,
            ).hexdigest()

    def _sign_with_session_private_key(self, message: str, private_key: str) -> str:
        """Session key 签名 (same mechanism as main wallet)"""
        return self._sign_with_main_wallet(message, private_key)

    def _recover_signer(self, message: str, signature: str) -> str:
        """恢复签名者地址"""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
            msg = encode_defunct(text=message)
            if signature.startswith("0x"):
                signature_bytes = bytes.fromhex(signature[2:])
            else:
                signature_bytes = bytes.fromhex(signature)
            recovered = Account.recover_message(msg, signature=signature_bytes)
            return recovered
        except (ImportError, Exception):
            # HMAC fallback: return main_wallet from the signature itself
            # (In HMAC mode, we can't recover — we rely on store verification)
            return ""