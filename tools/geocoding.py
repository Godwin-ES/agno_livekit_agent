"""Shared Open-Meteo place lookup."""

from __future__ import annotations

from typing import Any

import httpx

from .http import request_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_cache: dict[str, dict[str, Any] | None] = {}


async def geocode(place: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
    normalized = " ".join(place.split()).casefold()
    if not normalized:
        return None
    if client is None and normalized in _cache:
        return _cache[normalized]

    payload = await request_json(
        GEOCODING_URL,
        params={"name": place, "count": 1, "language": "en", "format": "json"},
        client=client,
    )
    results = payload.get("results")
    location = results[0] if isinstance(results, list) and results else None
    if client is None:
        _cache[normalized] = location
    return location
