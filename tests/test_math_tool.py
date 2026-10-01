from __future__ import annotations

import pytest

from tools.math import calculate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", 14),
        ("18% * 2450", 441),
        ("sqrt(81) + round(2.6)", 12),
        ("(10 - 4) ** 2", 36),
    ],
)
@pytest.mark.asyncio
async def test_calculate_returns_hand_checked_results(expression: str, expected: float) -> None:
    result = await calculate(expression)

    assert result["kind"] == "math"
    assert result["result"] == expected
    assert result["expression"] == expression
    assert result["say"]


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "().__class__.__base__",
        "unknown_name + 1",
        "2 ** 10000",
        "[1, 2, 3]",
    ],
)
@pytest.mark.asyncio
async def test_calculate_rejects_unsafe_or_expensive_expressions(expression: str) -> None:
    result = await calculate(expression)

    assert result["kind"] == "error"
    assert "couldn't calculate" in result["say"].lower()
