#!/usr/bin/env python3
"""
结算通道测试
"""

import os
import sys
import unittest
from decimal import Decimal

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

from settlement.base import PaymentRequest, PaymentResult
from settlement.channels.mock import MockChannel
from settlement.registry import ChannelRegistry


class TestMockChannel(unittest.TestCase):
    """Mock 结算通道测试"""

    def setUp(self):
        self.channel = MockChannel()
        # 设置测试余额
        self.channel.mint("0xbuyer", Decimal("1.0"))

    def test_channel_info(self):
        """测试通道基本信息"""
        self.assertEqual(self.channel.channel_id, "mock")
        self.assertEqual(self.channel.chain, "mock")
        self.assertTrue(self.channel.supports_escrow)

    def test_create_payment(self):
        """测试创建支付请求"""
        req = self.channel.create_payment(
            from_address="0xbuyer",
            to_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order-001",
        )
        self.assertEqual(req.from_address, "0xbuyer")
        self.assertEqual(req.to_address, "0xseller")
        self.assertEqual(req.amount, Decimal("0.01"))

    def test_execute_payment(self):
        """测试执行支付"""
        req = self.channel.create_payment(
            from_address="0xbuyer",
            to_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order-002",
        )
        # Mock 不需要真实签名
        result = self.channel.execute_payment(req, None, None)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.tx_hash)

    def test_escrow_lock(self):
        """测试托管锁定"""
        result = self.channel.escrow_lock(
            buyer_address="0xbuyer",
            seller_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order-003",
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.escrow_id)

    def test_escrow_release(self):
        """测试托管释放"""
        # 先锁定
        lock_result = self.channel.escrow_lock(
            buyer_address="0xbuyer",
            seller_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order-004",
        )
        self.assertTrue(lock_result.success)

        # 再释放
        release_result = self.channel.escrow_release(
            escrow_id=lock_result.escrow_id,
            to_address="0xseller",
            private_key="",
        )
        self.assertTrue(release_result.success)

    def test_escrow_refund(self):
        """测试托管退款"""
        # 先锁定
        lock_result = self.channel.escrow_lock(
            buyer_address="0xbuyer",
            seller_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order-005",
        )
        self.assertTrue(lock_result.success)

        # 再退款
        refund_result = self.channel.escrow_refund(
            escrow_id=lock_result.escrow_id,
            to_address="0xbuyer",
            private_key="",
        )
        self.assertTrue(refund_result.success)


class TestChannelRegistry(unittest.TestCase):
    """结算通道注册表测试"""

    def test_list_all(self):
        """测试列出所有通道"""
        channels = ChannelRegistry.list_all()
        self.assertIsInstance(channels, list)
        # 应该至少有 mock 通道
        mock_channel = next((c for c in channels if c.get("channel_id") == "mock"), None)
        self.assertIsNotNone(mock_channel)

    def test_get_mock_channel(self):
        """测试获取 Mock 通道"""
        channel = ChannelRegistry.get("mock")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.channel_id, "mock")

    def test_get_nonexistent_channel(self):
        """测试获取不存在的通道"""
        channel = ChannelRegistry.get("nonexistent")
        self.assertIsNone(channel)

    def test_list_supported_chains(self):
        """测试列出支持的链"""
        chains = ChannelRegistry.list_supported_chains()
        self.assertIsInstance(chains, list)
        self.assertIn("mock", chains)


class TestPaymentRequest(unittest.TestCase):
    """支付请求测试"""

    def test_create_request(self):
        """测试创建支付请求"""
        req = PaymentRequest(
            channel_id="mock",
            chain="mock",
            token="mock-token",
            from_address="0xbuyer",
            to_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order",
        )
        self.assertEqual(req.channel_id, "mock")
        self.assertEqual(req.amount, Decimal("0.01"))

    def test_request_with_description(self):
        """测试带描述的支付请求"""
        req = PaymentRequest(
            channel_id="mock",
            chain="mock",
            token="mock-token",
            from_address="0xbuyer",
            to_address="0xseller",
            amount=Decimal("0.01"),
            order_id="test-order",
            description="Test payment",
        )
        self.assertEqual(req.description, "Test payment")


class TestPaymentResult(unittest.TestCase):
    """支付结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = PaymentResult(
            success=True,
            channel_id="mock",
            order_id="test-order",
            tx_hash="0xabc123",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.tx_hash, "0xabc123")

    def test_failure_result(self):
        """测试失败结果"""
        result = PaymentResult(
            success=False,
            channel_id="mock",
            order_id="test-order",
            error="Insufficient balance",
        )
        self.assertFalse(result.success)
        self.assertIn("balance", result.error)


if __name__ == "__main__":
    unittest.main()
