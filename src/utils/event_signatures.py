"""
合约事件签名计算工具

计算 Solidity 事件的 keccak256 签名哈希。
"""


def keccak256(text: str) -> str:
    """
    计算 keccak256 哈希

    Args:
        text: 输入文本

    Returns:
        哈希值（hex，带 0x 前缀）

    Note:
        需要安装 pycryptodome: pip install pycryptodome
    """
    try:
        from Crypto.Hash import keccak
        k = keccak.new(digest_bits=256)
        k.update(text.encode('utf-8'))
        return '0x' + k.hexdigest()
    except ImportError:
        # Fallback: 使用 web3
        try:
            from web3 import Web3
            return Web3.keccak(text=text).hex()
        except ImportError:
            raise ImportError(
                "需要安装 pycryptodome 或 web3: "
                "pip install pycryptodome 或 pip install web3"
            )


# 托管合约事件签名
ESCROW_EVENT_SIGNATURES = {
    "EscrowCreated": "EscrowCreated(bytes32,address,address,uint256,address)",
    "EscrowFunded": "EscrowFunded(bytes32,bytes32)",
    "EscrowDelivered": "EscrowDelivered(bytes32,bytes)",
    "EscrowReleased": "EscrowReleased(bytes32)",
    "EscrowRefunded": "EscrowRefunded(bytes32)",
    "DisputeRaised": "DisputeRaised(bytes32,address,bytes)",
    "DisputeResolved": "DisputeResolved(bytes32,uint8)",
    "TimeoutClaimed": "TimeoutClaimed(bytes32)",
}


def compute_all_signatures() -> dict:
    """
    计算所有事件签名哈希

    Returns:
        {event_name: signature_hash}
    """
    result = {}
    for name, sig in ESCROW_EVENT_SIGNATURES.items():
        result[name] = keccak256(sig)
    return result


def print_signatures():
    """打印所有事件签名哈希"""
    signatures = compute_all_signatures()
    print("Event Signature Hashes:")
    print("-" * 80)
    for name, hash_val in signatures.items():
        sig = ESCROW_EVENT_SIGNATURES[name]
        print(f"{name}:")
        print(f"  Signature: {sig}")
        print(f"  Hash:      {hash_val}")
    print("-" * 80)
    print("\nCopy these hashes to chain_listener.py EVENT_SIGNATURES")


if __name__ == "__main__":
    print_signatures()
