"""
签名验证工具

验证以太坊钱包签名。
"""


def verify_eth_signature(
    message: str,
    signature: str,
    expected_address: str = None,
) -> dict:
    """
    验证以太坊签名

    Args:
        message: 原始消息
        signature: 签名（hex）
        expected_address: 预期地址（可选）

    Returns:
        {
            "valid": bool,
            "recovered_address": str,
            "error": str (if invalid)
        }

    Note:
        需要安装 eth-account 库: pip install eth-account
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        # 编码消息
        encoded = encode_defunct(text=message)

        # 恢复签名者地址
        recovered = Account.recover_message(encoded, signature=signature)

        # 验证地址
        if expected_address:
            expected_lower = expected_address.lower()
            recovered_lower = recovered.lower()
            valid = expected_lower == recovered_lower
        else:
            valid = True

        return {
            "valid": valid,
            "recovered_address": recovered,
        }

    except ImportError:
        return {
            "valid": False,
            "error": "eth-account not installed. Run: pip install eth-account",
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


def create_sign_message(
    action: str,
    timestamp: int,
    nonce: str = None,
) -> str:
    """
    创建待签名的消息

    Args:
        action: 操作类型 (e.g., "query_credit", "create_escrow")
        timestamp: 时间戳
        nonce: 随机数（防重放）

    Returns:
        待签名的消息字符串
    """
    if nonce:
        return f"CryptoMinds:{action}:{timestamp}:{nonce}"
    return f"CryptoMinds:{action}:{timestamp}"


def verify_api_signature(
    signature: str,
    address: str,
    action: str,
    timestamp: int,
    max_age_seconds: int = 300,
    nonce: str = None,
) -> dict:
    """
    验证 API 请求签名

    Args:
        signature: 签名
        address: 签名者地址
        action: 操作类型
        timestamp: 时间戳
        max_age_seconds: 最大有效时间（秒）
        nonce: 随机数

    Returns:
        {"valid": bool, "error": str (if invalid)}
    """
    import time

    # 检查时间戳
    now = int(time.time())
    if abs(now - timestamp) > max_age_seconds:
        return {
            "valid": False,
            "error": f"Timestamp expired. Max age: {max_age_seconds}s",
        }

    # 构建消息
    message = create_sign_message(action, timestamp, nonce)

    # 验证签名
    result = verify_eth_signature(message, signature, address)

    return result
