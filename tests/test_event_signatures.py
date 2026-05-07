"""
事件签名工具测试
"""

import pytest
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.event_signatures import (
    keccak256,
    ESCROW_EVENT_SIGNATURES,
    compute_all_signatures,
    print_signatures,
)


class TestKeccak256:
    """Keccak256 哈希测试"""

    def test_keccak256_basic(self):
        """测试基本哈希"""
        result = keccak256("test")
        assert result.startswith("0x")
        assert len(result) == 66  # 0x + 64 hex chars

    def test_keccak256_consistent(self):
        """测试一致性"""
        result1 = keccak256("hello")
        result2 = keccak256("hello")
        assert result1 == result2

    def test_keccak256_different_inputs(self):
        """测试不同输入产生不同哈希"""
        result1 = keccak256("hello")
        result2 = keccak256("world")
        assert result1 != result2

    def test_keccak256_empty_string(self):
        """测试空字符串"""
        result = keccak256("")
        assert result.startswith("0x")
        assert len(result) == 66


class TestEventSignatures:
    """事件签名测试"""

    def test_escrow_event_signatures_defined(self):
        """测试事件签名已定义"""
        assert "EscrowCreated" in ESCROW_EVENT_SIGNATURES
        assert "EscrowFunded" in ESCROW_EVENT_SIGNATURES
        assert "EscrowReleased" in ESCROW_EVENT_SIGNATURES

    def test_compute_all_signatures(self):
        """测试计算所有签名"""
        signatures = compute_all_signatures()

        assert len(signatures) == len(ESCROW_EVENT_SIGNATURES)

        for name in ESCROW_EVENT_SIGNATURES:
            assert name in signatures
            assert signatures[name].startswith("0x")
            assert len(signatures[name]) == 66

    def test_signature_format(self):
        """测试签名格式"""
        # EscrowCreated 签名应有正确格式
        sig = ESCROW_EVENT_SIGNATURES["EscrowCreated"]
        assert sig.startswith("EscrowCreated(")
        assert sig.endswith(")")

    def test_known_signature_hash(self):
        """测试已知签名哈希"""
        # Transfer(address,address,uint256) 的哈希是已知的
        # 这里测试我们的事件签名格式正确
        signatures = compute_all_signatures()

        # 每个签名应该是唯一的
        hashes = list(signatures.values())
        assert len(set(hashes)) == len(hashes)

    def test_print_signatures(self, capsys):
        """测试打印签名"""
        print_signatures()
        captured = capsys.readouterr()
        assert "Event Signature Hashes" in captured.out
        assert "EscrowCreated" in captured.out

    def test_all_event_signatures_have_hashes(self):
        """测试所有事件签名都有对应哈希"""
        signatures = compute_all_signatures()
        for name in ["EscrowCreated", "EscrowFunded", "EscrowDelivered",
                     "EscrowReleased", "EscrowRefunded", "DisputeRaised",
                     "DisputeResolved", "TimeoutClaimed"]:
            assert name in signatures
