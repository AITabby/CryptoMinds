"""Tests for config.py — wallet loading, env overrides, normalization."""
import json
import os
import tempfile
import pytest

from config import load_wallets, get_wallet_key, reload_wallets, WALLETS_FILE


@pytest.fixture(autouse=True)
def _no_cache_needed():
    """load_wallets is no longer cached — no cache clearing needed."""
    yield


@pytest.fixture
def wallet_file(tmp_path):
    """Create a temp wallets.json and patch WALLETS_FILE."""
    path = tmp_path / "wallets.json"
    original = WALLETS_FILE
    import config
    config.WALLETS_FILE = path
    yield path
    config.WALLETS_FILE = original


class TestLoadWallets:

    def test_missing_file_returns_empty(self, wallet_file):
        wallet_file.unlink(missing_ok=True)
        assert load_wallets() == {}

    def test_empty_file_returns_empty(self, wallet_file):
        wallet_file.write_text("{}")
        assert load_wallets() == {}

    def test_basic_load(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC", "private_key": "0xDEF"}
        }))
        result = load_wallets()
        assert "test" in result
        assert result["test"]["address"] == "0xABC"
        assert result["test"]["private_key"] == "0xDEF"

    def test_0x_prefix_auto_added(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC", "private_key": "DEF123"}
        }))
        result = load_wallets()
        assert result["test"]["private_key"].startswith("0x")

    def test_0x_prefix_not_double_added(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC", "private_key": "0xDEF123"}
        }))
        result = load_wallets()
        assert result["test"]["private_key"] == "0xDEF123"
        assert not result["test"]["private_key"].startswith("0x0x")

    def test_key_variant_privateKey(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC", "privateKey": "0xDEF"}
        }))
        result = load_wallets()
        assert result["test"]["private_key"] == "0xDEF"

    def test_key_variant_key(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC", "key": "0xDEF"}
        }))
        result = load_wallets()
        assert result["test"]["private_key"] == "0xDEF"

    def test_missing_address_defaults_empty(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"private_key": "0xDEF"}
        }))
        result = load_wallets()
        assert result["test"]["address"] == ""

    def test_missing_all_keys_defaults_empty(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "test": {"address": "0xABC"}
        }))
        result = load_wallets()
        assert result["test"]["private_key"] == ""

    def test_no_cache_returns_equal_data(self, wallet_file):
        """load_wallets is not cached but returns consistent data."""
        wallet_file.write_text(json.dumps({"test": {"address": "0x1", "private_key": "0x2"}}))
        first = load_wallets()
        second = load_wallets()
        assert first == second


class TestGetWalletKey:

    def test_env_var_override(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "mywallet": {"address": "0xABC", "private_key": "0xFILEKEY"}
        }))
        os.environ["WALLET_KEY_MYWALLET"] = "ENVENVKEY"
        result = get_wallet_key("mywallet")
        assert result == "0xENVENVKEY"
        del os.environ["WALLET_KEY_MYWALLET"]

    def test_env_var_0x_prefix(self, wallet_file):
        wallet_file.write_text("{}")
        os.environ["WALLET_KEY_TEST"] = "0xENVENVKEY"
        result = get_wallet_key("test")
        assert result == "0xENVENVKEY"
        del os.environ["WALLET_KEY_TEST"]

    def test_missing_name_returns_empty(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "other": {"address": "0xABC", "private_key": "0xDEF"}
        }))
        assert get_wallet_key("nonexistent") == ""

    def test_file_key_when_no_env(self, wallet_file):
        wallet_file.write_text(json.dumps({
            "mywallet": {"address": "0xABC", "private_key": "0xFILEKEY"}
        }))
        assert get_wallet_key("mywallet") == "0xFILEKEY"


class TestReloadWallets:

    def test_reload_picks_up_changes(self, wallet_file):
        wallet_file.write_text(json.dumps({"a": {"address": "0x1", "private_key": "0x2"}}))
        first = load_wallets()
        assert "a" in first

        wallet_file.write_text(json.dumps({"b": {"address": "0x3", "private_key": "0x4"}}))
        second = reload_wallets()
        assert "a" not in second
        assert "b" in second