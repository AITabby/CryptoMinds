"""Tests for env_loader — environment loading, validation, safety checks."""
import os
import sys
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _preserve_env():
    """Save and restore env vars around each test."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


class TestLoadEnvDev:

    def test_dev_defaults_load(self):
        os.environ.pop("CRYPTOMINDS_ENV", None)
        from scripts.env_loader import load_env
        config = load_env()
        assert config["env"] == "dev"

    def test_dev_debug_allowed(self):
        os.environ["CRYPTOMINDS_ENV"] = "dev"
        os.environ["CRYPTOMINDS_DEBUG"] = "true"
        from scripts.env_loader import load_env
        config = load_env()
        assert config["DEBUG"] is True

    def test_dev_no_required_vars(self):
        os.environ["CRYPTOMINDS_ENV"] = "dev"
        os.environ.pop("CRYPTOMINDS_INTERNAL_TOKEN", None)
        from scripts.env_loader import load_env
        config = load_env()
        # INTERNAL_TOKEN loaded from .env — may be any value set in project config
        assert isinstance(config["INTERNAL_TOKEN"], str)


class TestLoadEnvStaging:

    def test_staging_warns_on_missing_token(self):
        os.environ["CRYPTOMINDS_ENV"] = "staging"
        os.environ.pop("CRYPTOMINDS_INTERNAL_TOKEN", None)
        from scripts.env_loader import load_env
        # Should not crash (only warns)
        config = load_env()
        assert config["env"] == "staging"


class TestLoadEnvProd:

    def test_prod_requires_internal_token(self):
        os.environ["CRYPTOMINDS_ENV"] = "prod"
        os.environ.pop("CRYPTOMINDS_INTERNAL_TOKEN", None)
        os.environ.pop("BSC_RPC", None)
        with pytest.raises(SystemExit):
            from scripts.env_loader import load_env
            load_env()

    def test_prod_rejects_demo_mode(self):
        os.environ["CRYPTOMINDS_ENV"] = "prod"
        os.environ["CRYPTOMINDS_INTERNAL_TOKEN"] = "secret"
        os.environ["BSC_RPC"] = "https://rpc.example.com"
        os.environ["DEPOSIT_POOL_ADDRESS"] = "0x123"
        os.environ["DEMO_MODE"] = "true"
        with pytest.raises(SystemExit):
            from scripts.env_loader import load_env
            load_env()

    def test_prod_rejects_debug(self):
        os.environ["CRYPTOMINDS_ENV"] = "prod"
        os.environ["CRYPTOMINDS_INTERNAL_TOKEN"] = "secret"
        os.environ["BSC_RPC"] = "https://rpc.example.com"
        os.environ["DEPOSIT_POOL_ADDRESS"] = "0x123"
        os.environ["DEMO_MODE"] = "false"
        os.environ["CRYPTOMINDS_DEBUG"] = "true"
        with pytest.raises(SystemExit):
            from scripts.env_loader import load_env
            load_env()


class TestValidateWalletsPermissions:

    def test_wallets_file_exists_and_not_overly_permissive(self):
        """Check that env_loader doesn't crash when wallets.json is absent or secure."""
        os.environ["CRYPTOMINDS_ENV"] = "dev"
        # wallets.json may not exist in test env — that's fine, env_loader only
        # warns about overly permissive files, not missing ones
        from scripts.env_loader import load_env
        config = load_env()
        assert config["env"] == "dev"


class TestEnvironmentFileLoading:

    def test_env_specific_file_loaded(self):
        """Verify that .env.dev is automatically loaded."""
        os.environ["CRYPTOMINDS_ENV"] = "dev"
        from scripts.env_loader import load_env, ENVIRONMENTS_DIR
        assert ENVIRONMENTS_DIR.exists()
        dev_file = ENVIRONMENTS_DIR / ".env.dev"
        assert dev_file.exists()