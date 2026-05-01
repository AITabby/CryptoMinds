"""Tests for safe_calculator.py — the AST-based safe expression evaluator."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from safe_calculator import safe_eval


class TestBasicArithmetic:
    def test_addition(self):
        assert safe_eval("2 + 3") == 5

    def test_subtraction(self):
        assert safe_eval("10 - 4") == 6

    def test_multiplication(self):
        assert safe_eval("3 * 7") == 21

    def test_division(self):
        assert safe_eval("10 / 2") == 5.0

    def test_nested_parentheses(self):
        assert safe_eval("(10 - 4) * 2 / 3") == 4.0

    def test_unary_plus(self):
        assert safe_eval("+5") == 5

    def test_unary_minus(self):
        assert safe_eval("-3") == -3

    def test_decimal(self):
        assert safe_eval("0.5 + 0.3") == pytest.approx(0.8)


class TestDangerousExpressionsRejected:
    def test_exponentiation_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("2**3")

    def test_large_exponentiation_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("2**999999")

    def test_bitwise_xor_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("1 ^ 2")

    def test_function_call_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("__import__('os').system('ls')")

    def test_variable_access_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("a + 1")

    def test_builtin_access_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("len('abc')")

    def test_attribute_access_rejected(self):
        # 1.real raises SyntaxError at parse level
        with pytest.raises((ValueError, SyntaxError)):
            safe_eval("1.real")

    def test_string_constant_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("'hello'")

    def test_boolean_constant_accepted_as_int(self):
        # bool is subclass of int in Python, True=1, False=0
        assert safe_eval("True") == 1
        assert safe_eval("False") == 0


class TestLengthLimit:
    def test_expression_over_200_chars_rejected(self):
        long_expr = "1 + " * 100 + "1"
        with pytest.raises(ValueError):
            safe_eval(long_expr)

    def test_empty_expression_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("")

    def test_expression_at_limit_accepted(self):
        # 199-char expression should work
        expr = "1" + " + 1" * 49  # ~199 chars
        result = safe_eval(expr)
        assert result == pytest.approx(50)


class TestDivisionByZero:
    def test_division_by_zero_raises(self):
        with pytest.raises(Exception):
            safe_eval("1 / 0")