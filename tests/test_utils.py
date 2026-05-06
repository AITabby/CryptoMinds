"""
测试签名验证工具
"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


class TestSignatureVerification(unittest.TestCase):
    """签名验证测试"""

    def test_create_sign_message(self):
        """测试创建签名消息"""
        from src.utils.signature import create_sign_message

        msg1 = create_sign_message("query_credit", 1715040000)
        self.assertEqual(msg1, "CryptoMinds:query_credit:1715040000")

        msg2 = create_sign_message("create_escrow", 1715040000, "nonce123")
        self.assertEqual(msg2, "CryptoMinds:create_escrow:1715040000:nonce123")

    def test_verify_api_signature_expired(self):
        """测试过期签名"""
        from src.utils.signature import verify_api_signature
        import time

        # 使用过期的时间戳
        result = verify_api_signature(
            signature="0x123",
            address="0xabc",
            action="test",
            timestamp=int(time.time()) - 400,  # 400 秒前
            max_age_seconds=300,
        )

        self.assertFalse(result["valid"])
        self.assertIn("expired", result["error"])

    def test_verify_eth_signature_no_library(self):
        """测试无 eth-account 库的情况"""
        from src.utils.signature import verify_eth_signature

        with patch.dict("sys.modules", {"eth_account": None}):
            result = verify_eth_signature("test message", "0x123", "0xabc")
            # 应该返回错误（库未安装）
            self.assertFalse(result["valid"])


class TestEventSignatures(unittest.TestCase):
    """事件签名测试"""

    def test_escrow_event_signatures_defined(self):
        """测试事件签名定义"""
        from src.utils.event_signatures import ESCROW_EVENT_SIGNATURES

        self.assertIn("EscrowCreated", ESCROW_EVENT_SIGNATURES)
        self.assertIn("EscrowFunded", ESCROW_EVENT_SIGNATURES)
        self.assertIn("EscrowReleased", ESCROW_EVENT_SIGNATURES)
        self.assertIn("DisputeRaised", ESCROW_EVENT_SIGNATURES)

    def test_compute_all_signatures_structure(self):
        """测试签名计算结构"""
        from src.utils.event_signatures import compute_all_signatures

        with patch("src.utils.event_signatures.keccak256") as mock_keccak:
            mock_keccak.return_value = "0xabc123"

            result = compute_all_signatures()

            self.assertIn("EscrowCreated", result)
            self.assertEqual(result["EscrowCreated"], "0xabc123")


if __name__ == "__main__":
    unittest.main()
