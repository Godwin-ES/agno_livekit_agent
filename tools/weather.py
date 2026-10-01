"""Current conditions and short forecast from Open-Meteo."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import httpx

from .geocoding import geocode
from .http import request_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    61: "Rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorms",
    96: "Thunderstorms",
    99: "Thunderstorms",
}


def _condition(code: Any) -> str:
    try:
        return WEATHER_CODES.get(int(code), "Mixed conditions")
    except (TypeError, ValueError):
        return "Mixed conditions"


async def get_weather(
    city: str,
    units: Literal["celsius", "fahrenheit"] = "celsius",
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Use when the user asks for current weather or the next three days in a place."""
    try:
        location = await geocode(city, client=client)
        if not location:
            return {"kind": "error", "say": f"I couldn't find a place called {city}."}
        unit = "fahrenheit" if units.casefold().startswith("f") else "celsius"
        payload = await request_json(
            FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "timezone": location.get("timezone", "auto"),
                "temperature_unit": unit,
                "forecast_days": 3,
                "current": "temperature_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            },
            client=client,
        )
        current = payload.get("current", {})
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        forecast = [
            {
                "date": day,
                "high": round(highs[index]),
                "low": round(lows[index]),
                "condition": _condition(codes[index]),
            }
            for index, day in enumerate(dates[:3])
            if index < len(highs) and index < len(lows) and index < len(codes)
        ]
        temperature = round(float(current["temperature_2m"]))
        condition = _condition(current.get("weather_code"))
        symbol = "°F" if unit == "fahrenheit" else "°C"
        rain_day = next(
            (
                date.fromisoformat(item["date"]).strftime("%A")
                for item in forecast[1:]
                if any(word in item["condition"].lower() for word in ("rain", "shower", "thunder"))
            ),
            None,
        )
        say = f"It's {temperature}{symbol} and {condition.lower()} in {location['name']}."
        if rain_day:
            say += f" Rain is possible on {rain_day}."
        place = ", ".join(filter(None, [location.get("name"), location.get("country")]))
        return {
            "kind": "weather",
            "say": say,
            "place": place,
            "units": unit,
            "temperature": temperature,
            "condition": condition,
            "forecast": forecast,
        }
    except Exception:
        return {"kind": "error", "say": "I couldn't reach the weather service right now."}
