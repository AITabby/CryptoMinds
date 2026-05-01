"""Tests for Session Key authorization model, signing, and verification."""

import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from auth.session_key import SessionKey
from auth.session_signer import SessionSigner, SessionKeyError


def _make_session_key(**overrides):
    defaults = {
        "session_key_id": "sk-test-001",
        "main_wallet": "0xMainWallet",
        "agent_id": "agent-001",
        "available_chains": ["bsc", "mock"],
        "per_tx_limit": Decimal("0.5"),
        "total_quota": Decimal("10.0"),
        "total_used": Decimal("0"),
        "callable_actions": ["pay", "escrow", "deliver"],
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + 86400,
        "nonce": 0,
        "revoked": False,
        "session_private_key": "0xfakekey",
        "session_address": "0xFakeAddress",
        "authorization_signature": "0xfakesig",
    }
    for k, v in overrides.items():
        defaults[k] = v
    return SessionKey(**defaults)


class TestSessionKeyModel:
    def test_is_valid_not_revoked_not_expired(self):
        sk = _make_session_key()
        assert sk.is_valid()

    def test_is_valid_revoked(self):
        sk = _make_session_key(revoked=True)
        assert not sk.is_valid()

    def test_is_valid_expired(self):
        sk = _make_session_key(expires_at=int(time.time()) - 100)
        assert not sk.is_valid()

    def test_can_spend_within_limits(self):
        sk = _make_session_key()
        assert sk.can_spend(Decimal("0.3"), "bsc", "pay")

    def test_can_spend_over_per_tx_limit(self):
        sk = _make_session_key(per_tx_limit=Decimal("0.5"))
        assert not sk.can_spend(Decimal("1.0"), "bsc", "pay")

    def test_can_spend_over_total_quota(self):
        sk = _make_session_key(total_quota=Decimal("1.0"), total_used=Decimal("0.8"))
        assert not sk.can_spend(Decimal("0.3"), "bsc", "pay")

    def test_can_spend_unsupported_chain(self):
        sk = _make_session_key(available_chains=["bsc"])
        assert not sk.can_spend(Decimal("0.1"), "eth", "pay")

    def test_can_spend_unsupported_action(self):
        sk = _make_session_key(callable_actions=["pay"])
        assert not sk.can_spend(Decimal("0.1"), "bsc", "deliver")

    def test_authorization_message(self):
        sk = _make_session_key()
        msg = sk.authorization_message()
        assert "CryptoMinds session key authorization" in msg
        assert sk.agent_id in msg
        assert sk.session_address in msg

    def test_to_dict_excludes_private(self):
        sk = _make_session_key()
        d = sk.to_dict()
        assert "session_private_key" not in d

    def test_to_dict_includes_private(self):
        sk = _make_session_key()
        d = sk.to_dict(include_private=True)
        assert "session_private_key" in d


class TestSessionSigner:
    def test_create_session_key(self):
        store = MagicMock()
        signer = SessionSigner(store)
        # Mock eth_account for key derivation and signing
        with patch("auth.session_signer.SessionSigner._derive_key_pair",
                    return_value=("0xderivedkey", "0xDerivedAddr")), \
             patch("auth.session_signer.SessionSigner._sign_with_main_wallet",
                    return_value="0xauthsig"):
            sk = signer.create_session_key(
                main_wallet="0xMain",
                main_private_key="0xMainKey",
                agent_id="agent-1",
                chains=["bsc"],
                per_tx_limit=Decimal("0.5"),
                total_quota=Decimal("10"),
                actions=["pay"],
                validity_seconds=3600,
            )
        assert sk.agent_id == "agent-1"
        assert sk.session_address == "0xDerivedAddr"
        assert sk.authorization_signature == "0xauthsig"
        assert not sk.revoked
        store.save.assert_called_once_with(sk)

    def test_sign_with_valid_session_key(self):
        sk = _make_session_key()
        signer = SessionSigner()
        # Mock verification to pass
        with patch.object(signer, "verify_session_authorization", return_value=True), \
             patch.object(signer, "_sign_with_session_private_key", return_value="0xsig"):
            result = signer.sign_with_session_key(sk, {
                "chain": "bsc",
                "action": "pay",
                "amount": "0.1",
            })
        assert result["signature"] == "0xsig"
        assert result["session_key_id"] == sk.session_key_id
        assert sk.total_used == Decimal("0.1")

    def test_sign_revoked_key_fails(self):
        sk = _make_session_key(revoked=True)
        signer = SessionSigner()
        with pytest.raises(SessionKeyError, match="已被撤销"):
            signer.sign_with_session_key(sk, {"chain": "bsc", "action": "pay", "amount": "0.1"})

    def test_sign_expired_key_fails(self):
        sk = _make_session_key(expires_at=int(time.time()) - 100)
        signer = SessionSigner()
        with pytest.raises(SessionKeyError, match="已过期"):
            signer.sign_with_session_key(sk, {"chain": "bsc", "action": "pay", "amount": "0.1"})

    def test_sign_over_per_tx_limit_fails(self):
        sk = _make_session_key(per_tx_limit=Decimal("0.5"))
        signer = SessionSigner()
        with patch.object(signer, "verify_session_authorization", return_value=True):
            with pytest.raises(SessionKeyError, match="权限不足"):
                signer.sign_with_session_key(sk, {
                    "chain": "bsc", "action": "pay", "amount": "1.0"
                })

    def test_sign_over_quota_fails(self):
        sk = _make_session_key(total_quota=Decimal("1.0"), total_used=Decimal("0.9"))
        signer = SessionSigner()
        with patch.object(signer, "verify_session_authorization", return_value=True):
            with pytest.raises(SessionKeyError, match="权限不足"):
                signer.sign_with_session_key(sk, {
                    "chain": "bsc", "action": "pay", "amount": "0.2"
                })

    def test_sign_unsupported_chain_fails(self):
        sk = _make_session_key(available_chains=["bsc"])
        signer = SessionSigner()
        with patch.object(signer, "verify_session_authorization", return_value=True):
            with pytest.raises(SessionKeyError, match="权限不足"):
                signer.sign_with_session_key(sk, {
                    "chain": "eth", "action": "pay", "amount": "0.1"
                })

    def test_sign_unsupported_action_fails(self):
        sk = _make_session_key(callable_actions=["pay"])
        signer = SessionSigner()
        with patch.object(signer, "verify_session_authorization", return_value=True):
            with pytest.raises(SessionKeyError, match="权限不足"):
                signer.sign_with_session_key(sk, {
                    "chain": "bsc", "action": "deliver", "amount": "0.1"
                })

    def test_revoke_session_key(self):
        store = MagicMock()
        sk = _make_session_key()
        store.get = MagicMock(return_value=sk)
        signer = SessionSigner(store)
        with patch.object(signer, "_sign_with_main_wallet", return_value="0xrevokesig"), \
             patch.object(signer, "_recover_signer", return_value="0xMainWallet"):
            result = signer.revoke_session_key("sk-test-001", "0xMainWallet", "0xkey")
        assert result["ok"]
        assert sk.revoked is True
        assert sk.nonce == 1

    def test_revoke_by_wrong_wallet_fails(self):
        store = MagicMock()
        sk = _make_session_key()
        store.get = MagicMock(return_value=sk)
        signer = SessionSigner(store)
        with patch.object(signer, "_sign_with_main_wallet", return_value="0xrevokesig"), \
             patch.object(signer, "_recover_signer", return_value="0xOtherWallet"):
            result = signer.revoke_session_key("sk-test-001", "0xOtherWallet", "0xkey")
        assert "error" in result

    def test_increase_quota(self):
        store = MagicMock()
        sk = _make_session_key()
        store.get = MagicMock(return_value=sk)
        signer = SessionSigner(store)
        with patch.object(signer, "_sign_with_main_wallet", return_value="0xquotasig"), \
             patch.object(signer, "_recover_signer", return_value="0xMainWallet"):
            result = signer.increase_quota("sk-test-001", Decimal("5.0"), "0xMainWallet", "0xkey")
        assert result["ok"]
        assert sk.total_quota == Decimal("15.0")


class TestSqliteSessionKeyStore:
    def test_save_and_get(self):
        import tempfile
        from data.sqlite_store import SqliteSessionKeyStore
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)
        sk = _make_session_key()
        store.save(sk)
        retrieved = store.get("sk-test-001")
        assert retrieved is not None
        assert retrieved.agent_id == "agent-001"
        assert retrieved.total_quota == Decimal("10.0")

    def test_revoke(self):
        import tempfile
        from data.sqlite_store import SqliteSessionKeyStore
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)
        sk = _make_session_key()
        store.save(sk)
        store.revoke("sk-test-001")
        retrieved = store.get("sk-test-001")
        assert retrieved.revoked is True
        assert retrieved.nonce == 1

    def test_update_usage(self):
        import tempfile
        from data.sqlite_store import SqliteSessionKeyStore
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)
        sk = _make_session_key()
        store.save(sk)
        store.update_usage("sk-test-001", Decimal("0.5"))
        retrieved = store.get("sk-test-001")
        assert retrieved.total_used == Decimal("0.5")

    def test_increase_quota_via_store(self):
        import tempfile
        from data.sqlite_store import SqliteSessionKeyStore
        db_path = tempfile.mktemp(suffix=".db")
        store = SqliteSessionKeyStore(db_path)
        sk = _make_session_key()
        store.save(sk)
        store.increase_quota("sk-test-001", Decimal("5.0"))
        retrieved = store.get("sk-test-001")
        assert retrieved.total_quota == Decimal("15.0")