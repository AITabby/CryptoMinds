"""Tests for verification gates — signal_content, compute_result, token_delivery."""
from decimal import Decimal
import json
import pytest

from verification.base import TaskInput, TaskOutput, VerificationResult
from verification.gates.signal_content import SignalStreamGate, ContentDeliveryGate
from verification.gates.compute_result import ComputeResultGate
from verification.gates.token_delivery import TokenDeliveryGate


# ── SignalStreamGate ──

class TestSignalStreamGateValidateInput:

    def test_valid_input(self):
        gate = SignalStreamGate()
        inp = TaskInput(
            task_type="signal_stream", buyer_wallet="0xB",
            params={"signal_type": "price", "duration_hours": 1},
        )
        valid, msg = gate.validate_input(inp)
        assert valid is True

    def test_missing_signal_type(self):
        gate = SignalStreamGate()
        inp = TaskInput(task_type="signal_stream", buyer_wallet="0xB", params={})
        valid, msg = gate.validate_input(inp)
        assert valid is False

    def test_missing_duration_hours(self):
        gate = SignalStreamGate()
        inp = TaskInput(
            task_type="signal_stream", buyer_wallet="0xB",
            params={"signal_type": "price"},
        )
        valid, msg = gate.validate_input(inp)
        assert valid is False

    def test_wrong_task_type(self):
        gate = SignalStreamGate()
        inp = TaskInput(task_type="wrong", buyer_wallet="0xB", params={"signal_type": "price", "duration_hours": 1})
        valid, msg = gate.validate_input(inp)
        assert valid is False


class TestSignalStreamGateValidateOutput:

    def test_valid_output_with_extra_signals(self):
        gate = SignalStreamGate()
        out = TaskOutput(task_type="signal_stream", data="", extra={"signals": [{"type": "price", "timestamp": 100}]})
        valid, msg = gate.validate_output(out)
        assert valid is True

    def test_valid_output_with_data_json(self):
        gate = SignalStreamGate()
        out = TaskOutput(task_type="signal_stream", data=json.dumps([{"type": "price", "timestamp": 100}]), extra={})
        valid, msg = gate.validate_output(out)
        assert valid is True

    def test_missing_output_data(self):
        gate = SignalStreamGate()
        out = TaskOutput(task_type="signal_stream", data="", extra={})
        valid, msg = gate.validate_output(out)
        assert valid is False


class TestSignalStreamGateVerify:

    def test_verify_with_valid_signals(self):
        import time
        gate = SignalStreamGate(min_signals=1)
        inp = TaskInput(
            task_type="signal_stream", buyer_wallet="0xB",
            params={"signal_type": "price", "duration_hours": 1},
        )
        # Use a current timestamp so delay check passes
        now = int(time.time())
        out = TaskOutput(task_type="signal_stream", data="", extra={"signals": [{"type": "price", "timestamp": now}]})
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score > 0

    def test_verify_insufficient_signals(self):
        gate = SignalStreamGate(min_signals=3)
        inp = TaskInput(
            task_type="signal_stream", buyer_wallet="0xB",
            params={"signal_type": "price", "duration_hours": 1},
        )
        out = TaskOutput(task_type="signal_stream", data="", extra={"signals": [{"type": "price", "timestamp": 100}]})
        result = gate.verify(inp, out)
        assert result.success is False

    def test_verify_invalid_format(self):
        gate = SignalStreamGate(min_signals=1)
        inp = TaskInput(
            task_type="signal_stream", buyer_wallet="0xB",
            params={"signal_type": "price", "duration_hours": 1},
        )
        out = TaskOutput(task_type="signal_stream", data="", extra={"signals": [{"no_type": True}]})
        result = gate.verify(inp, out)
        assert result.success is False


class TestSignalStreamGateParseSignals:

    def test_parse_from_extra(self):
        gate = SignalStreamGate()
        signals = [{"type": "a", "timestamp": 1}]
        out = TaskOutput(task_type="signal_stream", data="", extra={"signals": signals})
        parsed = gate._parse_signals(out)
        assert len(parsed) == 1

    def test_parse_from_data_json(self):
        gate = SignalStreamGate()
        signals = [{"type": "a", "timestamp": 1}]
        out = TaskOutput(task_type="signal_stream", data=json.dumps(signals), extra={})
        parsed = gate._parse_signals(out)
        assert len(parsed) == 1


# ── ContentDeliveryGate ──

class TestContentDeliveryGateValidateInput:

    def test_valid_input(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "text"},
        )
        valid, msg = gate.validate_input(inp)
        assert valid is True

    def test_missing_content_type(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(task_type="content_delivery", buyer_wallet="0xB", params={})
        valid, msg = gate.validate_input(inp)
        assert valid is False


class TestContentDeliveryGateVerifyText:

    def test_verify_text_with_enough_words(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "text"},
        )
        out = TaskOutput(task_type="content_delivery", data="This is a test text content with enough words to pass the check")
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score > 0

    def test_verify_text_short_content(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "text"},
        )
        out = TaskOutput(task_type="content_delivery", data="short")
        result = gate.verify(inp, out)
        assert result.score >= 0


class TestContentDeliveryGateVerifyImage:

    def test_verify_image_with_base64(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "image"},
        )
        out = TaskOutput(task_type="content_delivery", data="data:image/png;base64,ABC123")
        result = gate.verify(inp, out)
        assert result.success is True

    def test_verify_image_with_file_hash(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "image"},
        )
        out = TaskOutput(task_type="content_delivery", data="", file_hash="sha256abc")
        result = gate.verify(inp, out)
        assert result.success is True


class TestContentDeliveryGateVerifyAudioVideo:

    def test_verify_audio_with_file_hash(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "audio"},
        )
        out = TaskOutput(task_type="content_delivery", data="", file_hash="sha256abc")
        result = gate.verify(inp, out)
        assert result.success is True

    def test_verify_video_with_file_hash(self):
        gate = ContentDeliveryGate()
        inp = TaskInput(
            task_type="content_delivery", buyer_wallet="0xB",
            params={"content_type": "video"},
        )
        out = TaskOutput(task_type="content_delivery", data="", file_hash="sha256abc")
        result = gate.verify(inp, out)
        assert result.success is True


# ── ComputeResultGate ──

class TestComputeResultGateValidateInput:

    def test_valid_input(self):
        gate = ComputeResultGate()
        inp = TaskInput(
            task_type="compute_result", buyer_wallet="0xB",
            params={"compute_type": "inference"},
        )
        valid, msg = gate.validate_input(inp)
        assert valid is True

    def test_missing_compute_type(self):
        gate = ComputeResultGate()
        inp = TaskInput(task_type="compute_result", buyer_wallet="0xB", params={})
        valid, msg = gate.validate_input(inp)
        assert valid is False


class TestComputeResultGateCompareResults:

    def test_numeric_match(self):
        gate = ComputeResultGate()
        result = gate._compare_results("42", "42", tolerance=0.1)
        assert result["match"] is True
        assert result["score"] > 0

    def test_numeric_within_tolerance(self):
        gate = ComputeResultGate()
        result = gate._compare_results("42", "43", tolerance=0.05)
        assert result["match"] is True

    def test_numeric_outside_tolerance(self):
        gate = ComputeResultGate()
        result = gate._compare_results("42", "50", tolerance=0.05)
        assert result["match"] is False

    def test_json_object_match(self):
        gate = ComputeResultGate()
        result = gate._compare_results(
            json.dumps({"a": 1}), json.dumps({"a": 1}), tolerance=0.1
        )
        assert result["match"] is True

    def test_string_similarity_fallback(self):
        gate = ComputeResultGate()
        result = gate._compare_results("hello world foo bar baz", "hello earth foo bar baz", tolerance=0.1)
        # Falls to Jaccard similarity since not parseable as single JSON value
        assert "match" in result


class TestComputeResultGateStringSimilarity:

    def test_identical_strings(self):
        gate = ComputeResultGate()
        score = gate._string_similarity("hello world", "hello world")
        assert score == 1.0

    def test_completely_different_strings(self):
        gate = ComputeResultGate()
        score = gate._string_similarity("aaa", "bbb")
        assert score == 0.0


class TestComputeResultGateCheckVerifyConditions:

    def test_non_empty_condition(self):
        gate = ComputeResultGate()
        out = TaskOutput(task_type="compute_result", data="some data")
        assert gate._check_verify_conditions(out, "non_empty") is True

    def test_non_empty_condition_empty(self):
        gate = ComputeResultGate()
        out = TaskOutput(task_type="compute_result", data="")
        assert gate._check_verify_conditions(out, "non_empty") is False

    def test_valid_json_condition(self):
        gate = ComputeResultGate()
        out = TaskOutput(task_type="compute_result", data=json.dumps({"key": "val"}))
        assert gate._check_verify_conditions(out, "valid_json") is True

    def test_positive_condition(self):
        gate = ComputeResultGate()
        out = TaskOutput(task_type="compute_result", data="42")
        assert gate._check_verify_conditions(out, "positive") is True


class TestComputeResultGateVerify:

    def test_verify_with_expected_result(self):
        gate = ComputeResultGate()
        inp = TaskInput(
            task_type="compute_result", buyer_wallet="0xB",
            params={"compute_type": "inference", "expected_result": "42"},
        )
        out = TaskOutput(task_type="compute_result", data="42")
        result = gate.verify(inp, out)
        assert result.success is True

    def test_verify_with_verify_function(self):
        gate = ComputeResultGate()
        inp = TaskInput(
            task_type="compute_result", buyer_wallet="0xB",
            params={"compute_type": "inference", "verify_function": "non_empty"},
        )
        out = TaskOutput(task_type="compute_result", data="some result")
        result = gate.verify(inp, out)
        assert result.success is True


# ── TokenDeliveryGate extended ──

class TestTokenDeliveryGateCalculateMinExpected:

    def test_with_token_amount(self):
        gate = TokenDeliveryGate(slippage=0.05)
        inp = TaskInput(task_type="token_delivery", buyer_wallet="0xB", chain="mock")
        # token_amount is a field on TaskOutput, not extra
        out = TaskOutput(task_type="token_delivery", data="", token_amount="1000")
        result = gate._calculate_min_expected(inp, out)
        assert result == Decimal("950")

    def test_without_token_amount(self):
        gate = TokenDeliveryGate(slippage=0.05)
        inp = TaskInput(task_type="token_delivery", buyer_wallet="0xB", chain="mock")
        out = TaskOutput(task_type="token_delivery", data="", extra={})
        result = gate._calculate_min_expected(inp, out)
        assert result == Decimal("0")


class TestTokenDeliveryGateVerifyMock:

    def test_verify_mock_chain(self):
        gate = TokenDeliveryGate()
        inp = TaskInput(
            task_type="token_delivery", buyer_wallet="0xB", chain="mock",
            params={"token_address": "0xTKN"},
            amount=Decimal("0.01"),
        )
        out = TaskOutput(
            task_type="token_delivery", data="",
            tx_hash="0x1", token_address="0xTKN", token_amount="100",
        )
        result = gate.verify(inp, out)
        assert result.success is True
        assert result.score == 1.0