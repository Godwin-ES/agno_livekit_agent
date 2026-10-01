"""Custom tools exposed to the Agno voice agent, with explicit schemas."""

from __future__ import annotations

from typing import Any

from .currency import convert_currency
from .math import calculate
from .schema import explicit_tool, number, string
from .time import get_time
from .weather import get_weather

UNITS = {"type": "string", "enum": ["celsius", "fahrenheit"]}


async def _weather(city: str, units: str = "celsius") -> dict[str, Any]:
    return await get_weather(city, units)  # type: ignore[arg-type]


async def _time(place: str) -> dict[str, Any]:
    return await get_time(place)


async def _currency(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    return await convert_currency(amount, from_currency, to_currency)


async def _calculate(expression: str) -> dict[str, Any]:
    return await calculate(expression)


ALL_TOOLS = [
    explicit_tool(
        "get_weather",
        "Use when the user asks for current weather or the next three days in a place.",
        _weather,
        {"city": string("City or place name, e.g. Lagos"), "units": UNITS},
        ["city"],
    ),
    explicit_tool(
        "get_time",
        "Use when the user asks for the current local time in a city or place.",
        _time,
        {"place": string("City or place name, e.g. Tokyo")},
        ["place"],
    ),
    explicit_tool(
        "convert_currency",
        "Use when the user asks to convert money between currencies.",
        _currency,
        {
            "amount": number("Amount to convert", minimum=0),
            "from_currency": string("ISO currency code to convert from, e.g. USD"),
            "to_currency": string("ISO currency code to convert to, e.g. EUR"),
        },
        ["amount", "from_currency", "to_currency"],
    ),
    explicit_tool(
        "calculate",
        "Use for arithmetic, percentages, tips, and short numeric calculations.",
        _calculate,
        {"expression": string("Arithmetic expression, e.g. 18% * 2450")},
        ["expression"],
    ),
]

__all__ = ["ALL_TOOLS", "calculate", "convert_currency", "get_time", "get_weather"]
