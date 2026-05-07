"""
签名工具测试
"""

import time

from src.utils.signature import (
    create_sign_message,
    verify_api_signature,
    verify_eth_signature,
)


class TestCreateSignMessage:
    """创建签名消息测试"""

    def test_create_message_basic(self):
        """测试基本消息"""
        message = create_sign_message("query_credit", 1234567890)
        assert message == "CryptoMinds:query_credit:1234567890"

    def test_create_message_with_nonce(self):
        """测试带 nonce 的消息"""
        message = create_sign_message("create_escrow", 1234567890, "abc123")
        assert message == "CryptoMinds:create_escrow:1234567890:abc123"

    def test_create_message_different_actions(self):
        """测试不同操作"""
        for action in ["query_credit", "create_escrow", "arbitrate_vote"]:
            message = create_sign_message(action, 1000)
            assert action in message


class TestVerifyApiSignature:
    """API 签名验证测试"""

    def test_expired_timestamp(self):
        """测试过期时间戳"""
        # 10 分钟前的时间戳
        old_timestamp = int(time.time()) - 600

        result = verify_api_signature(
            signature="0x123",
            address="0xabc",
            action="query_credit",
            timestamp=old_timestamp,
            max_age_seconds=300,
        )

        assert result["valid"] is False
        assert "expired" in result["error"].lower()

    def test_future_timestamp(self):
        """测试未来时间戳"""
        # 10 分钟后的时间戳
        future_timestamp = int(time.time()) + 600

        result = verify_api_signature(
            signature="0x123",
            address="0xabc",
            action="query_credit",
            timestamp=future_timestamp,
            max_age_seconds=300,
        )

        assert result["valid"] is False

    def test_valid_timestamp(self):
        """测试有效时间戳"""
        # 当前时间戳
        now = int(time.time())

        result = verify_api_signature(
            signature="0x" + "a" * 130,  # 假签名
            address="0xabc",
            action="query_credit",
            timestamp=now,
        )

        # 时间戳检查通过，但签名验证失败（因为是假签名）
        # 错误不应是时间戳过期
        if not result["valid"]:
            assert "expired" not in result.get("error", "").lower()


class TestVerifyEthSignature:
    """以太坊签名验证测试"""

    def test_invalid_signature_format(self):
        """测试无效签名格式"""
        result = verify_eth_signature(
            message="test",
            signature="invalid",
            expected_address="0xabc",
        )
        assert result["valid"] is False

    def test_no_expected_address(self):
        """测试无预期地址"""
        # 无预期地址时，只要签名格式正确就返回 valid=True
        # 这里用假签名测试格式错误的情况
        result = verify_eth_signature(
            message="test",
            signature="invalid",
            expected_address=None,
        )
        assert result["valid"] is False
