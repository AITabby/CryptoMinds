"""
CryptoMinds 环境变量加载器
启动时加载 .env 并校验，缺失关键配置时报错退出
"""
import os
import stat
import sys
from pathlib import Path

def load_env():
    """加载 .env 文件，返回配置字典"""
    project_root = Path(__file__).parent.parent

    # 尝试加载 .env（从项目根目录）
    try:
        from dotenv import load_dotenv
        env_path = project_root / '.env'
        load_dotenv(env_path)
    except ImportError:
        pass  # 没装 python-dotenv 就用系统环境变量

    errors = []
    config = {}

    # BSC RPC（有默认值，不强制）
    config['BSC_RPC'] = os.getenv('BSC_RPC', 'https://bsc-dataseed1.binance.org/')

    # 演示模式
    config['DEMO_MODE'] = os.getenv('DEMO_MODE', 'false').lower() in ('1', 'true', 'yes')

    # 调试模式
    config['DEBUG'] = os.getenv('DEBUG', 'false').lower() in ('1', 'true', 'yes')

    # 检查 wallets.json 是否存在
    wallets_path = project_root / 'wallets.json'
    if not wallets_path.exists():
        errors.append("wallets.json 不存在，请确保钱包配置文件在项目根目录")
    elif wallets_path.stat().st_mode & stat.S_IROTH:
        errors.append("wallets.json 权限过于宽松，请运行: chmod 600 wallets.json")

    if errors:
        for err in errors:
            print(f"[ENV-ERROR] {err}", file=sys.stderr)
        sys.exit(1)

    return config


if __name__ == '__main__':
    cfg = load_env()
    print("[ENV-OK] Configuration loaded successfully.")
    print(f"  BSC_RPC={cfg['BSC_RPC']}")
    print(f"  DEMO_MODE={cfg['DEMO_MODE']}")
    print(f"  DEBUG={cfg['DEBUG']}")
