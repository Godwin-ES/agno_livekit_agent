"""Shared HTTP client and bounded retry behavior for voice tools."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

HTTP_TIMEOUT_SECONDS = 4.0
_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
            headers={"User-Agent": "EchoRun-Voice-Agent/1.0"},
        )
    return _client


async def request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch JSON with one quick retry for transient transport/server failures."""
    http = client or get_http_client()
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await http.get(url, params=params)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt == 0 and (
                not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500
            ):
                await asyncio.sleep(0.05)
                continue
            raise
    assert last_error is not None
    raise last_error
