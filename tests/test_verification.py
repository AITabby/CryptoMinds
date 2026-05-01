#!/usr/bin/env python3
"""
验证门测试
"""

import os
import sys
import unittest
from decimal import Decimal

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

from verification.base import TaskInput, TaskOutput, VerificationResult
from verification.gates.token_delivery import TokenDeliveryGate
from verification.gates.data_delivery import DataDeliveryGate
from verification.gates.compute_result import ComputeResultGate


class TestTokenDeliveryGate(unittest.TestCase):
    """Token 交付验证门测试"""

    def setUp(self):
        self.gate = TokenDeliveryGate()

    def test_gate_info(self):
        """测试验证门基本信息"""
        self.assertEqual(self.gate.gate_id, "token_delivery")
        self.assertEqual(self.gate.task_type, "token_delivery")
        self.assertIn("mock", self.gate.supported_chains)

    def test_validate_input_missing_wallet(self):
        """测试缺少钱包地址"""
        inp = TaskInput(
            task_type="token_delivery",
            buyer_wallet="",
            amount=Decimal("0.01"),
        )
        valid, msg = self.gate.validate_input(inp)
        self.assertFalse(valid)
        self.assertIn("买家钱包", msg)

    def test_validate_input_invalid_amount(self):
        """测试无效金额"""
        inp = TaskInput(
            task_type="token_delivery",
            buyer_wallet="0xbuyer",
            amount=Decimal("0"),
        )
        valid, msg = self.gate.validate_input(inp)
        self.assertFalse(valid)
        self.assertIn("大于 0", msg)

    def test_validate_output_missing_tx_hash(self):
        """测试缺少交易哈希"""
        out = TaskOutput(
            task_type="token_delivery",
            seller_wallet="0xseller",
            tx_hash="",
        )
        valid, msg = self.gate.validate_output(out)
        self.assertFalse(valid)
        self.assertIn("交易哈希", msg)

    def test_mock_chain_verification_success(self):
        """测试 Mock 链验证成功"""
        inp = TaskInput(
            task_type="token_delivery",
            buyer_wallet="0xbuyer",
            seller_wallet="0xseller",
            chain="mock",
            amount=Decimal("0.01"),
        )
        out = TaskOutput(
            task_type="token_delivery",
            seller_wallet="0xseller",
            tx_hash="0xabc123",
            token_address="0xtoken",
            token_amount="1000000",
        )
        result = self.gate.verify(inp, out)
        self.assertTrue(result.success)
        self.assertEqual(result.score, 1.0)
        self.assertIn("mock", result.evidence)

    def test_unsupported_chain(self):
        """测试不支持的链"""
        inp = TaskInput(
            task_type="token_delivery",
            buyer_wallet="0xbuyer",
            chain="unknown_chain",
            amount=Decimal("0.01"),
        )
        out = TaskOutput(
            task_type="token_delivery",
            seller_wallet="0xseller",
            tx_hash="0xabc123",
        )
        result = self.gate.verify(inp, out)
        self.assertFalse(result.success)
        self.assertIn("不支持", result.error)


class TestDataDeliveryGate(unittest.TestCase):
    """数据交付验证门测试"""

    def setUp(self):
        self.gate = DataDeliveryGate()

    def test_gate_info(self):
        """测试验证门基本信息"""
        self.assertEqual(self.gate.gate_id, "data_delivery")

    def test_validate_output_missing_data(self):
        """测试缺少数据"""
        out = TaskOutput(
            task_type="data_delivery",
            seller_wallet="0xseller",
            data="",
        )
        valid, msg = self.gate.validate_output(out)
        self.assertFalse(valid)

    def test_verification_with_data(self):
        """测试有数据的验证"""
        inp = TaskInput(
            task_type="data_delivery",
            buyer_wallet="0xbuyer",
            amount=Decimal("0.01"),
            params={"data_type": "raw"},  # 需要指定 data_type
        )
        out = TaskOutput(
            task_type="data_delivery",
            seller_wallet="0xseller",
            data="test data content",
        )
        result = self.gate.verify(inp, out)
        self.assertTrue(result.success)


class TestComputeResultGate(unittest.TestCase):
    """计算结果验证门测试"""

    def setUp(self):
        self.gate = ComputeResultGate()

    def test_gate_info(self):
        """测试验证门基本信息"""
        self.assertEqual(self.gate.gate_id, "compute_result")

    def test_verification_with_result(self):
        """测试有结果的验证"""
        inp = TaskInput(
            task_type="compute_result",
            buyer_wallet="0xbuyer",
            amount=Decimal("0.01"),
            params={"compute_type": "inference", "expected_format": "json"},
        )
        out = TaskOutput(
            task_type="compute_result",
            seller_wallet="0xseller",
            data='{"result": 42}',
        )
        result = self.gate.verify(inp, out)
        self.assertTrue(result.success)


class TestVerificationResult(unittest.TestCase):
    """验证结果测试"""

    def test_to_dict(self):
        """测试转换为字典"""
        result = VerificationResult(
            success=True,
            score=0.95,
            gate_id="test_gate",
            task_type="test_task",
            chain="mock",
            evidence={"key": "value"},
        )
        d = result.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["score"], 0.95)
        self.assertEqual(d["evidence"]["key"], "value")

    def test_error_result(self):
        """测试错误结果"""
        result = VerificationResult(
            success=False,
            gate_id="test_gate",
            task_type="test_task",
            error="Something went wrong",
        )
        self.assertFalse(result.success)
        self.assertIn("wrong", result.error)


if __name__ == "__main__":
    unittest.main()
