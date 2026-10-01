from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from tools.currency import convert_currency
from tools.time import get_time
from tools.weather import get_weather


ClientFactory = Callable[[httpx.MockTransport], httpx.AsyncClient]


@pytest.mark.asyncio
async def test_weather_returns_current_conditions_and_three_days(client_factory: ClientFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200,
                json={"results": [{"name": "Lagos", "country": "Nigeria", "latitude": 6.45, "longitude": 3.4, "timezone": "Africa/Lagos"}]},
            )
        return httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 29.2, "weather_code": 3},
                "daily": {
                    "time": ["2026-10-01", "2026-10-02", "2026-10-03"],
                    "temperature_2m_max": [31, 30, 29],
                    "temperature_2m_min": [24, 24, 23],
                    "weather_code": [3, 61, 80],
                },
            },
        )

    result = await get_weather("Lagos", client=client_factory(httpx.MockTransport(handler)))

    assert result == {
        "kind": "weather",
        "say": "It's 29°C and overcast in Lagos. Rain is possible on Friday.",
        "place": "Lagos, Nigeria",
        "units": "celsius",
        "temperature": 29,
        "condition": "Overcast",
        "forecast": [
            {"date": "2026-10-01", "high": 31, "low": 24, "condition": "Overcast"},
            {"date": "2026-10-02", "high": 30, "low": 24, "condition": "Rain"},
            {"date": "2026-10-03", "high": 29, "low": 23, "condition": "Rain showers"},
        ],
    }


@pytest.mark.asyncio
async def test_weather_handles_unknown_place(client_factory: ClientFactory) -> None:
    client = client_factory(httpx.MockTransport(lambda _: httpx.Response(200, json={"results": []})))

    result = await get_weather("Atlantis", client=client)

    assert result["kind"] == "error"
    assert "Atlantis" in result["say"]


@pytest.mark.asyncio
async def test_weather_handles_timeout(client_factory: ClientFactory) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    result = await get_weather("Lagos", client=client_factory(httpx.MockTransport(timeout)))

    assert result["kind"] == "error"
    assert "weather service" in result["say"].lower()


@pytest.mark.asyncio
async def test_time_uses_geocoded_timezone(client_factory: ClientFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_factory(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"results": [{"name": "Tokyo", "country": "Japan", "latitude": 35.7, "longitude": 139.7, "timezone": "Asia/Tokyo"}]},
            )
        )
    )
    monkeypatch.setattr("tools.time._utc_now", lambda: __import__("datetime").datetime(2026, 10, 1, 12, 0, tzinfo=__import__("datetime").UTC))

    result = await get_time("Tokyo", client=client)

    assert result["kind"] == "time"
    assert result["time"] == "9:00 PM"
    assert result["utc_offset"] == "+09:00"
    assert result["say"] == "It's 9:00 PM in Tokyo."


@pytest.mark.asyncio
async def test_currency_converts_supported_pair(client_factory: ClientFactory) -> None:
    client = client_factory(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"amount": 150, "base": "EUR", "date": "2026-09-30", "rates": {"USD": 176.25}})
        )
    )

    result = await convert_currency(150, "eur", "usd", client=client)

    assert result == {
        "kind": "currency",
        "say": "150 EUR is about 176.25 USD.",
        "amount": 150.0,
        "from": "EUR",
        "to": "USD",
        "converted": 176.25,
        "rate": 1.175,
        "date": "2026-09-30",
    }


@pytest.mark.asyncio
async def test_currency_reports_unsupported_currency(client_factory: ClientFactory) -> None:
    client = client_factory(
        httpx.MockTransport(lambda _: httpx.Response(400, json={"message": "not supported"}))
    )

    result = await convert_currency(200, "USD", "NGN", client=client)

    assert result["kind"] == "error"
    assert "doesn't support NGN" in result["say"]
