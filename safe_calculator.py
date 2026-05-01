"""Safe arithmetic expression evaluator for compute tasks."""
import ast
import operator

MAX_EXPRESSION_LENGTH = 200

SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

SAFE_UNOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_eval(expression: str) -> float:
    """Safely evaluate a numeric expression.

    Only allows: digits, +, -, *, /, parentheses, decimal points.
    No exponentiation, no bitwise ops, no function calls, no variable access.
    """
    if not expression or len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"Expression too long (max {MAX_EXPRESSION_LENGTH} chars)")

    tree = ast.parse(expression, mode='eval')

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Only numeric constants allowed")
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_UNOPS:
                raise ValueError(f"Unary operator {op_type.__name__} not allowed")
            return SAFE_UNOPS[op_type](_eval(node.operand))
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_BINOPS:
                raise ValueError(f"Binary operator {op_type.__name__} not allowed")
            left = _eval(node.left)
            right = _eval(node.right)
            return SAFE_BINOPS[op_type](left, right)
        else:
            raise ValueError(f"Node type {type(node).__name__} not allowed")

    return _eval(tree)