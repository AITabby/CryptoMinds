"""
CryptoMinds 环境管理
- 按 CRYPTOMINDS_ENV (dev/staging/prod) 自动加载对应 .env
- 启动校验：缺失关键配置时报错退出
- 配置指纹：打印当前环境摘要
"""
import os
import stat
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ENVIRONMENTS_DIR = PROJECT_ROOT / "environments"

REQUIRED_PROD_VARS = [
    "CRYPTOMINDS_INTERNAL_TOKEN",
    "ADMIN_SECRET",
    "BSC_RPC",
    "DEPOSIT_POOL_ADDRESS",
]

REQUIRED_STAGING_VARS = [
    "CRYPTOMINDS_INTERNAL_TOKEN",
    "ADMIN_SECRET",
    "BSC_RPC",
]


def _load_env_file(env_path: Path):
    """Load a .env file into os.environ (python-dotenv if available, else manual)."""
    if not env_path.exists():
        return False
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # Manual fallback: parse KEY=VALUE lines
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value
    return True


def load_env():
    """Load environment config and validate. Returns config dict."""
    # 1. Determine environment
    env_name = os.getenv("CRYPTOMINDS_ENV", "dev").lower()

    # 2. Load base .env (project root, override=False so explicit env vars win)
    _load_env_file(PROJECT_ROOT / ".env")

    # 3. Load environment-specific file (overrides base for that env)
    env_file = ENVIRONMENTS_DIR / f".env.{env_name}"
    loaded = _load_env_file(env_file)
    if not loaded and env_name != "dev":
        logger.warning(f"Environment file {env_file} not found, using base .env only")

    # 4. Read final config from os.environ (env-specific + user overrides win)
    config = {
        "env": env_name,
        "BSC_RPC": os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org/"),
        "DEMO_MODE": os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes"),
        "DEBUG": os.getenv("CRYPTOMINDS_DEBUG", "false").lower() in ("1", "true", "yes"),
        "API_PORT": int(os.getenv("CRYPTOMINDS_API_PORT", "3458")),
        "LOG_LEVEL": os.getenv("CRYPTOMINDS_LOG_LEVEL", "INFO").upper(),
        "LOG_JSON": os.getenv("CRYPTOMINDS_LOG_JSON", "false").lower() == "true",
        "INTERNAL_TOKEN": os.getenv("CRYPTOMINDS_INTERNAL_TOKEN", ""),
    }

    # 5. Validate
    errors = _validate(env_name, config)

    if errors:
        for err in errors:
            logger.error(f"[ENV-ERROR] {err}")
        if env_name == "prod":
            logger.critical("Production startup aborted due to configuration errors")
            sys.exit(1)
        elif env_name == "staging":
            logger.warning("Staging has configuration warnings — proceed with caution")

    # 6. Print config summary (no secrets)
    logger.info(f"[ENV-OK] Environment: {env_name}")
    logger.info(f"  BSC_RPC={config['BSC_RPC']}")
    logger.info(f"  DEMO_MODE={config['DEMO_MODE']}")
    logger.info(f"  DEBUG={config['DEBUG']}")
    logger.info(f"  API_PORT={config['API_PORT']}")
    logger.info(f"  LOG_LEVEL={config['LOG_LEVEL']}")
    logger.info(f"  INTERNAL_TOKEN={'<set>' if config['INTERNAL_TOKEN'] else '<empty>'}")

    return config


def _validate(env_name: str, config: dict) -> list:
    """Validate required config based on environment."""
    errors = []

    # Check required vars per environment
    if env_name == "prod":
        for var in REQUIRED_PROD_VARS:
            if not os.getenv(var):
                errors.append(f"Missing required env var: {var}")
    elif env_name == "staging":
        for var in REQUIRED_STAGING_VARS:
            if not os.getenv(var):
                errors.append(f"Missing required env var: {var}")

    # Always check wallets.json permissions
    wallets_path = PROJECT_ROOT / "wallets.json"
    if wallets_path.exists() and (wallets_path.stat().st_mode & stat.S_IROTH):
        errors.append("wallets.json permissions too open — run: chmod 600 wallets.json")

    # Prod must not be in demo mode
    if env_name == "prod" and config["DEMO_MODE"]:
        errors.append("DEMO_MODE must be false in production")

    # Prod must not have debug
    if env_name == "prod" and config["DEBUG"]:
        errors.append("CRYPTOMINDS_DEBUG must be false in production")

    # Prod requires JSON logging
    if env_name == "prod" and not config["LOG_JSON"]:
        errors.append("CRYPTOMINDS_LOG_JSON must be true in production")

    # INTERNAL_TOKEN must not be weak
    weak_tokens = {"", "dev-internal-token", "test-token", "secret", "password", "admin"}
    if config["INTERNAL_TOKEN"].lower() in weak_tokens:
        if env_name in ("prod", "staging"):
            errors.append(f"CRYPTOMINDS_INTERNAL_TOKEN is too weak ('{config['INTERNAL_TOKEN'][:8]}...') — use a strong random value")

    # ADMIN_SECRET must not be weak
    admin_secret = os.getenv("ADMIN_SECRET", "")
    weak_admin = {"", "admin", "secret", "password", "test"}
    if admin_secret.lower() in weak_admin:
        if env_name in ("prod", "staging"):
            errors.append(f"ADMIN_SECRET is too weak ('{admin_secret[:8]}...') — use a strong random value")

    return errors


if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging()
    cfg = load_env()