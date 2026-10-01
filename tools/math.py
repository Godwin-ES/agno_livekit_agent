"""A deliberately small, safe arithmetic expression evaluator."""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Callable

MAX_ABS_VALUE = 1e100
MAX_EXPONENT = 12
MAX_EXPRESSION_LENGTH = 160

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "sqrt": math.sqrt,
}


def _bounded(value: float) -> float:
    if not math.isfinite(float(value)) or abs(float(value)) > MAX_ABS_VALUE:
        raise ValueError("result is too large")
    return value


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return _bounded(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > MAX_EXPONENT or abs(left) > 1e6):
            raise ValueError("exponent is too large")
        return _bounded(_BINARY[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _bounded(_UNARY[type(node.op)](_evaluate(node.operand)))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
        and len(node.args) == 1
    ):
        return _bounded(_FUNCTIONS[node.func.id](_evaluate(node.args[0])))
    raise ValueError("unsupported expression")


async def calculate(expression: str) -> dict[str, Any]:
    """Use for arithmetic, percentages, tips, and short numeric calculations."""
    try:
        if len(expression) > MAX_EXPRESSION_LENGTH:
            raise ValueError("expression is too long")
        normalized = re.sub(r"(?P<number>(?:\d+(?:\.\d+)?))%(?=\s*[*/+-])", r"(\g<number> / 100)", expression)
        normalized = re.sub(r"\bpercent\s+of\b", "/ 100 *", normalized, flags=re.IGNORECASE)
        value = _evaluate(ast.parse(normalized, mode="eval"))
        result: int | float = int(value) if float(value).is_integer() else round(float(value), 10)
        return {
            "kind": "math",
            "say": f"The answer is {result:g}.",
            "expression": expression,
            "result": result,
        }
    except Exception:
        return {"kind": "error", "say": "I couldn't calculate that safely."}
