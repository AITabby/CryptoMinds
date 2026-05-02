"""Tests for verification/gates/data_delivery.py — covers all uncovered lines."""
import hashlib
import json

import pytest

from verification.base import TaskInput, TaskOutput, VerificationResult
from verification.gates.data_delivery import DataDeliveryGate


# ── validate_input ──

class TestDataDeliveryValidateInput:

    def test_missing_data_type(self):
        """Line 51: missing data_type param returns False."""
        gate = DataDeliveryGate()
        inp = TaskInput(task_type="data_delivery", buyer_wallet="0xB", params={})
        valid, msg = gate.validate_input(inp)
        assert valid is False
        assert "缺少数据类型" in msg

    def test_valid_input_with_data_type(self):
        gate = DataDeliveryGate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "analysis"},
        )
        valid, msg = gate.validate_input(inp)
        assert valid is True

    def test_wrong_task_type(self):
        """Line 51: task_type mismatch."""
        gate = DataDeliveryGate()
        inp = TaskInput(task_type="wrong_type", buyer_wallet="0xB", params={"data_type": "analysis"})
        valid, msg = gate.validate_input(inp)
        assert valid is False
        assert "任务类型不匹配" in msg

    def test_missing_buyer_wallet(self):
        """Line 48: missing buyer_wallet."""
        gate = DataDeliveryGate()
        inp = TaskInput(task_type="data_delivery", buyer_wallet="", params={"data_type": "analysis"})
        valid, msg = gate.validate_input(inp)
        assert valid is False


# ── validate_output ──

class TestDataDeliveryValidateOutput:

    def test_missing_file_hash_and_data(self):
        """Line 67-68: both file_hash and data missing."""
        gate = DataDeliveryGate()
        out = TaskOutput(task_type="data_delivery", data="", file_hash="")
        valid, msg = gate.validate_output(out)
        assert valid is False
        assert "缺少数据或文件哈希" in msg

    def test_valid_with_data_only(self):
        gate = DataDeliveryGate()
        out = TaskOutput(task_type="data_delivery", data="some data", file_hash="")
        valid, msg = gate.validate_output(out)
        assert valid is True

    def test_valid_with_file_hash_only(self):
        gate = DataDeliveryGate()
        out = TaskOutput(task_type="data_delivery", data="", file_hash="sha256abc")
        valid, msg = gate.validate_output(out)
        assert valid is True

    def test_valid_with_both(self):
        gate = DataDeliveryGate()
        out = TaskOutput(task_type="data_delivery", data="content", file_hash="sha256abc")
        valid, msg = gate.validate_output(out)
        assert valid is True


# ── verify — full path ──

class TestDataDeliveryVerify:

    def _make_gate(self, min_size=0, max_size=100*1024*1024):
        return DataDeliveryGate(min_size_bytes=min_size, max_size_bytes=max_size)

    def test_hash_mismatch(self):
        """Line 119: expected_hash != actual_hash."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw", "expected_hash": "abc123"},
        )
        out = TaskOutput(task_type="data_delivery", data="hello world", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "哈希不匹配" in result.error

    def test_data_too_small(self):
        """Line 132: data_size < min_size_bytes."""
        gate = self._make_gate(min_size=100)
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(task_type="data_delivery", data="short", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "数据太小" in result.error

    def test_data_too_large(self):
        """Line 140: data_size > max_size_bytes."""
        gate = self._make_gate(max_size=10)
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(task_type="data_delivery", data="a very long string that exceeds max", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "数据太大" in result.error

    def test_format_validation_invalid_json(self):
        """Lines 150-159: expected_format=json but data is not JSON."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw", "expected_format": "json"},
        )
        out = TaskOutput(task_type="data_delivery", data="not json at all", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "不是有效的 JSON" in result.error

    def test_format_validation_invalid_csv(self):
        """Lines 150-159: expected_format=csv but data lacks commas/newlines."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw", "expected_format": "csv"},
        )
        out = TaskOutput(task_type="data_delivery", data="just text no csv", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "不是有效的 CSV" in result.error

    def test_format_validation_invalid_base64(self):
        """Lines 150-159: expected_format=base64 but data is not base64."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw", "expected_format": "base64"},
        )
        out = TaskOutput(task_type="data_delivery", data="!!!notbase64!!!", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is False
        assert "不是有效的 Base64" in result.error

    def test_quality_score_in_extra(self):
        """Lines 163-167: quality_score from output.extra sets result score."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(
            task_type="data_delivery", data="valid data", file_hash="",
            extra={"quality_score": "0.85"},
        )
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score == 0.85

    def test_quality_score_non_numeric_falls_back_to_1(self):
        """Lines 163-167: quality_score that can't convert to float -> score=1.0."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(
            task_type="data_delivery", data="valid data", file_hash="",
            extra={"quality_score": "not_a_number"},
        )
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score == 1.0

    def test_verify_success_no_expected_hash_no_format(self):
        """Successful verify when data is present with no hash/format constraints."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(task_type="data_delivery", data="some valid data", file_hash="")
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score == 1.0
        assert result.evidence["data_type"] == "raw"

    def test_verify_success_with_matching_hash(self):
        """Data hash matches expected_hash."""
        data = "hello world"
        expected_hash = hashlib.sha256(data.encode()).hexdigest()
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw", "expected_hash": expected_hash},
        )
        out = TaskOutput(task_type="data_delivery", data=data, file_hash="")
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.evidence.get("actual_hash") == expected_hash

    def test_verify_no_data_but_file_hash_present(self):
        """When output has file_hash but no data, verify still succeeds (no data checks)."""
        gate = self._make_gate()
        inp = TaskInput(
            task_type="data_delivery", buyer_wallet="0xB",
            params={"data_type": "raw"},
        )
        out = TaskOutput(task_type="data_delivery", data="", file_hash="sha256abc")
        result = gate.verify(inp, out)
        assert result.success is True


# ── _validate_format ──

class TestValidateFormat:

    def _gate(self):
        return DataDeliveryGate()

    def test_json_valid(self):
        """Lines 180-186: valid JSON."""
        valid, msg = self._gate()._validate_format(json.dumps({"key": "val"}), "json")
        assert valid is True
        assert "JSON" in msg

    def test_json_invalid(self):
        """Lines 180-186: invalid JSON."""
        valid, msg = self._gate()._validate_format("not json", "json")
        assert valid is False
        assert "不是有效的 JSON" in msg

    def test_csv_valid(self):
        """Lines 188-192: valid CSV (has newline and comma)."""
        valid, msg = self._gate()._validate_format("a,b\n1,2", "csv")
        assert valid is True

    def test_csv_invalid(self):
        """Lines 188-192: invalid CSV (no newline or comma)."""
        valid, msg = self._gate()._validate_format("just text", "csv")
        assert valid is False

    def test_text_always_valid(self):
        """Lines 194-196: text format always passes."""
        valid, msg = self._gate()._validate_format("anything", "text")
        assert valid is True

    def test_base64_valid(self):
        """Lines 198-204: valid base64."""
        import base64
        encoded = base64.b64encode(b"hello").decode()
        valid, msg = self._gate()._validate_format(encoded, "base64")
        assert valid is True

    def test_base64_invalid(self):
        """Lines 198-204: invalid base64."""
        valid, msg = self._gate()._validate_format("!!!invalid!!!", "base64")
        assert valid is False

    def test_other_format_skips_check(self):
        """Line 206: unknown format defaults to pass."""
        valid, msg = self._gate()._validate_format("anything", "xml")
        assert valid is True
        assert "格式检查跳过" in msg