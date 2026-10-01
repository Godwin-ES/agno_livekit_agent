from __future__ import annotations

import asyncio
import json

import httpx

import pytest

from tools.external import _is_public_url, read_article, run_blocking_tool


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "http://localhost/internal",
    ],
)
@pytest.mark.asyncio
async def test_article_url_guard_rejects_non_public_destinations(url: str) -> None:
    assert await _is_public_url(url) is False


@pytest.mark.asyncio
async def test_blocking_tools_have_an_overall_deadline() -> None:
    def slow() -> str:
        import time

        time.sleep(0.1)
        return "late"

    result = await run_blocking_tool(slow, timeout=0.01)

    assert result["kind"] == "error"
    assert "timed out" in result["say"].lower()


def _transport(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_article_reader_refuses_a_redirect_to_a_private_address(client_factory) -> None:
    client = client_factory(
        _transport({"http://93.184.215.14/story": httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})})
    )

    result = await read_article("http://93.184.215.14/story", client=client)

    assert result == {"kind": "error", "say": "I can't open that page."}


@pytest.mark.asyncio
async def test_article_reader_refuses_an_oversized_page(client_factory, monkeypatch) -> None:
    monkeypatch.setattr("tools.external.ARTICLE_MAX_BYTES", 100)
    client = client_factory(
        _transport({"http://93.184.215.14/big": httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 500)})
    )

    result = await read_article("http://93.184.215.14/big", client=client)

    assert result["kind"] == "error"


@pytest.mark.asyncio
async def test_article_reader_parses_a_public_page(client_factory) -> None:
    html = b"<html><head><title>Launch</title></head><body><article><h1>Launch</h1>" + b"<p>The rocket launched on time and reached orbit after a smooth ascent.</p>" * 20 + b"</article></body></html>"
    client = client_factory(
        _transport({"http://93.184.215.14/news": httpx.Response(200, headers={"content-type": "text/html"}, content=html)})
    )

    result = await read_article("http://93.184.215.14/news", client=client)

    assert isinstance(result, str)
    assert "reached orbit" in json.loads(result)["text"]
