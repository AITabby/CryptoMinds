"""
x402 支付协议入口

兼容现有 x402_pay.py 接口，底层使用结算通道抽象。
"""

import os
import json
from decimal import Decimal
from typing import Dict, Optional, Tuple
from pathlib import Path

from .registry import ChannelRegistry
from .base import PaymentRequest, PaymentResult
from .channels.bsc_native import BSCNativeChannel
from .channels.mock import MockChannel


# ── 初始化默认通道 ──────────────────────────────────

def init_default_channels():
    """初始化默认通道"""
    if not ChannelRegistry.get("bsc-native"):
        test_mode = os.getenv("SETTLEMENT_TEST_MODE", "false").lower() == "true"
        ChannelRegistry.register(BSCNativeChannel(test_mode=test_mode))

    if not ChannelRegistry.get("mock"):
        ChannelRegistry.register(MockChannel())


# 自动初始化
init_default_channels()


# ── 钱包加载 ────────────────────────────────────────

WALLETS_FILE = Path(__file__).parent.parent / "wallets.json"


def load_wallets() -> Dict:
    """加载钱包配置"""
    if WALLETS_FILE.exists():
        return json.loads(WALLETS_FILE.read_text())
    return {}


def get_wallet_address(name: str) -> Optional[str]:
    """获取钱包地址"""
    wallets = load_wallets()
    return wallets.get(name, {}).get("address")


def get_wallet_key(name: str) -> Optional[str]:
    """获取钱包私钥"""
    wallets = load_wallets()
    info = wallets.get(name, {})
    return info.get("private_key") or info.get("privateKey") or info.get("key")


# ── x402 支付接口（兼容旧版）─────────────────────────

def x402_pay(
    from_name: str,
    to_name: str,
    amount_bnb: float,
    order_id: str,
    description: str = "",
    channel_id: str = "bsc-native"
) -> Tuple[bool, str, Dict]:
    """
    执行 x402 支付

    兼容现有接口，底层使用结算通道抽象。

    Args:
        from_name: 发送方钱包名称
        to_name: 接收方钱包名称
        amount_bnb: BNB 数量
        order_id: 订单 ID
        description: 描述
        channel_id: 结算通道 ID（默认 bsc-native）

    Returns:
        (success, tx_hash, payment_info)
    """
    wallets = load_wallets()

    if from_name not in wallets:
        return False, "", {"error": f"未知发送方: {from_name}"}
    if to_name not in wallets:
        return False, "", {"error": f"未知接收方: {to_name}"}

    from_addr = wallets[from_name]["address"]
    to_addr = wallets[to_name]["address"]
    private_key = get_wallet_key(from_name)

    if not private_key:
        return False, "", {"error": f"找不到 {from_name} 的私钥"}

    # 获取通道
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return False, "", {"error": f"未知通道: {channel_id}"}

    # 创建支付请求
    request = channel.create_payment(
        from_address=from_addr,
        to_address=to_addr,
        amount=Decimal(str(amount_bnb)),
        order_id=order_id,
        description=description,
    )

    # 签名
    signature = channel.sign_payment(request, private_key)

    # 执行
    result = channel.execute_payment(request, signature, private_key)

    # 返回兼容格式
    if result.success:
        return True, result.tx_hash, result.to_dict()
    else:
        return False, "", {"error": result.error}


def verify_x402_payment(payment_info: Dict) -> Tuple[bool, str]:
    """
    验证 x402 支付

    Args:
        payment_info: 支付结果信息

    Returns:
        (valid, message)
    """
    channel_id = payment_info.get("channel_id", "bsc-native")
    channel = ChannelRegistry.get(channel_id)

    if not channel:
        return False, f"未知通道: {channel_id}"

    # 构造 PaymentResult
    result = PaymentResult(
        success=payment_info.get("success", True),
        tx_hash=payment_info.get("tx_hash", ""),
        channel_id=channel_id,
        chain=payment_info.get("chain", channel.chain),
        token=payment_info.get("token", channel.token),
        from_address=payment_info.get("from", payment_info.get("from_address", "")),
        to_address=payment_info.get("to", payment_info.get("to_address", "")),
        amount=Decimal(str(payment_info.get("amount_bnb", payment_info.get("amount", 0)))),
        order_id=payment_info.get("order_id", ""),
        nonce=payment_info.get("nonce", ""),
        signature=payment_info.get("signature", ""),
        block_number=payment_info.get("block", payment_info.get("block_number", 0)),
        proof=payment_info.get("proof", {}),
    )

    return channel.verify_payment(result)


def get_bnb_balance(address: str) -> float:
    """查询 BNB 余额"""
    channel = ChannelRegistry.get("bsc-native")
    if channel:
        return float(channel.get_balance(address))
    return 0.0


# ── 托管接口 ────────────────────────────────────────

def escrow_lock(
    buyer_name: str,
    seller_name: str,
    amount: float,
    order_id: str,
    channel_id: str = "mock"
) -> Tuple[bool, str, Dict]:
    """
    锁定资金到托管

    Args:
        buyer_name: 买家钱包名称
        seller_name: 卖家钱包名称
        amount: 金额
        order_id: 订单 ID
        channel_id: 通道 ID（默认 mock，因为 BSC 需要前端调用合约）

    Returns:
        (success, escrow_id, info)
    """
    wallets = load_wallets()

    buyer_addr = get_wallet_address(buyer_name)
    seller_addr = get_wallet_address(seller_name)

    if not buyer_addr or not seller_addr:
        return False, "", {"error": "找不到钱包地址"}

    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return False, "", {"error": f"未知通道: {channel_id}"}

    result = channel.escrow_lock(
        buyer_address=buyer_addr,
        seller_address=seller_addr,
        amount=Decimal(str(amount)),
        order_id=order_id,
    )

    if result.success:
        return True, result.escrow_id, {
            "escrow_id": result.escrow_id,
            "amount": str(result.amount),
            "channel_id": channel_id,
        }
    else:
        return False, "", {"error": result.error}


def escrow_release(
    escrow_id: str,
    to_name: str,
    channel_id: str = "mock"
) -> Tuple[bool, str, Dict]:
    """
    释放托管资金

    Args:
        escrow_id: 托管 ID
        to_name: 接收方钱包名称
        channel_id: 通道 ID

    Returns:
        (success, tx_hash, info)
    """
    to_addr = get_wallet_address(to_name)
    private_key = get_wallet_key(to_name)

    if not to_addr:
        return False, "", {"error": "找不到钱包地址"}

    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return False, "", {"error": f"未知通道: {channel_id}"}

    result = channel.escrow_release(escrow_id, to_addr, private_key or "")

    if result.success:
        return True, result.tx_hash, {
            "tx_hash": result.tx_hash,
            "amount": str(result.amount),
        }
    else:
        return False, "", {"error": result.error}


def escrow_refund(
    escrow_id: str,
    to_name: str,
    channel_id: str = "mock"
) -> Tuple[bool, str, Dict]:
    """
    退款托管资金

    Args:
        escrow_id: 托管 ID
        to_name: 接收方钱包名称（通常是买家）
        channel_id: 通道 ID

    Returns:
        (success, tx_hash, info)
    """
    to_addr = get_wallet_address(to_name)
    private_key = get_wallet_key(to_name)

    if not to_addr:
        return False, "", {"error": "找不到钱包地址"}

    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return False, "", {"error": f"未知通道: {channel_id}"}

    result = channel.escrow_refund(escrow_id, to_addr, private_key or "")

    if result.success:
        return True, result.tx_hash, {
            "tx_hash": result.tx_hash,
            "amount": str(result.amount),
        }
    else:
        return False, "", {"error": result.error}


# ── 测试 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== x402 支付测试（多通道版本）===")

    # 列出所有通道
    print("\n支持的通道:")
    for c in ChannelRegistry.list_all():
        print(f"  • {c['channel_id']}: {c['chain']}/{c['token']} (托管: {c['supports_escrow']})")

    # 测试 Mock 通道
    print("\n测试 Mock 通道:")
    mock = ChannelRegistry.get("mock")
    mock.set_balance("0xbuyer", Decimal("1.0"))
    mock.set_balance("0xseller", Decimal("0.5"))

    print(f"  买家余额: {mock.get_balance('0xbuyer')}")
    print(f"  卖家余额: {mock.get_balance('0xseller')}")

    # 执行支付
    success, tx_hash, info = x402_pay(
        from_name="buyer",
        to_name="seller",
        amount_bnb=0.1,
        order_id="test-001",
        channel_id="mock"
    )
    print(f"  支付结果: {success}, tx: {tx_hash[:20]}...")