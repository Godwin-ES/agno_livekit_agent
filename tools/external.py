"""Agno's built-in toolkits, wrapped for a voice call.

The toolkits (DuckDuckGo, Wikipedia, yfinance, Hacker News) are synchronous:
called directly they block the event loop that also carries the audio. Each
call here runs in a worker thread with one overall deadline, so a slow
service becomes a short spoken apology instead of dead air. A thread can't be
killed, so a timed-out call finishes in the background and its result is
discarded.

Articles are fetched here, not by newspaper4k: its own fetcher follows any
URL, and the URL comes from the model, which can be steered by a web page or
by the caller. ``read_article`` only fetches public http(s) addresses,
re-checks every redirect, and caps the time and size of the download.
Residual risk: the address is checked when resolved, and httpx resolves it
again to connect, so a DNS record that changes in between (rebinding) isn't
caught.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

TOOL_TIMEOUT_SECONDS = 4.0
ARTICLE_MAX_BYTES = 2_000_000
ARTICLE_MAX_REDIRECTS = 3
ARTICLE_TEXT_CHARS = 6000


def _error(say: str) -> dict[str, Any]:
    return {"kind": "error", "say": say}


async def run_blocking_tool(
    function: Callable[..., Any], *args: Any, timeout: float = TOOL_TIMEOUT_SECONDS, **kwargs: Any
) -> Any:
    """Run a synchronous toolkit call off the event loop, within ``timeout`` seconds."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(function, *args, **kwargs), timeout)
    except TimeoutError:
        return _error("That service timed out. Let's try something else.")
    except Exception:
        return _error("That service isn't responding right now.")


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _is_public_url(url: str) -> bool:
    """True only for an http(s) URL whose host resolves solely to public addresses."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    host = parts.hostname
    try:
        return _is_public_address(host)
    except ValueError:
        pass  # a name, not an IP literal
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except (socket.gaierror, UnicodeError, OSError):
        return False
    addresses = {info[4][0] for info in infos}
    try:
        return bool(addresses) and all(_is_public_address(address) for address in addresses)
    except ValueError:
        return False


async def _fetch_public_html(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch a page, re-validating each redirect hop and capping its size."""
    current = url
    for _ in range(ARTICLE_MAX_REDIRECTS + 1):
        if not await _is_public_url(current):
            return None
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                return None
            if "html" not in response.headers.get("content-type", "html"):
                return None
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > ARTICLE_MAX_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    return None


def _parse_article(url: str, html: str) -> dict[str, Any] | None:
    import newspaper

    article = newspaper.Article(url)
    article.download(input_html=html)
    article.parse()
    if not article.text:
        return None
    data: dict[str, Any] = {"title": article.title, "url": url, "text": article.text[:ARTICLE_TEXT_CHARS]}
    if article.authors:
        data["authors"] = article.authors
    if article.publish_date:
        data["publish_date"] = article.publish_date.isoformat()
    return data


async def read_article(
    url: str, *, client: httpx.AsyncClient | None = None, timeout: float = TOOL_TIMEOUT_SECONDS
) -> dict[str, Any] | str:
    """Read a public web article and return its title and text as JSON."""

    async def fetch_and_parse() -> dict[str, Any] | str:
        http = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), headers={"User-Agent": "EchoRun-Voice-Agent/1.0"}
        )
        try:
            html = await _fetch_public_html(url, http)
        finally:
            if client is None:
                await http.aclose()
        if html is None:
            return _error("I can't open that page.")
        data = await asyncio.to_thread(_parse_article, url, html)
        if data is None:
            return _error("I couldn't find any article text on that page.")
        return json.dumps(data)

    try:
        return await asyncio.wait_for(fetch_and_parse(), timeout)
    except TimeoutError:
        return _error("That page took too long to load.")
    except Exception:
        return _error("I couldn't read that page.")


def toolkit_functions() -> list[Any]:
    """The built-in toolkits' functions the demo uses, async and deadline-bound."""
    from agno.tools.duckduckgo import DuckDuckGoTools
    from agno.tools.hackernews import HackerNewsTools
    from agno.tools.wikipedia import WikipediaTools
    from agno.tools.yfinance import YFinanceTools

    from .schema import explicit_tool, string

    search = DuckDuckGoTools(fixed_max_results=5, timeout=4)
    wikipedia = WikipediaTools()
    finance = YFinanceTools(include_tools=["get_current_stock_price", "get_company_info"])
    hacker_news = HackerNewsTools(enable_get_top_stories=True, enable_get_user_details=False)
    symbol = {"symbol": string("Stock ticker symbol, e.g. NVDA")}

    async def web_search(query: str) -> Any:
        return await run_blocking_tool(search.web_search, query)

    async def search_news(query: str) -> Any:
        return await run_blocking_tool(search.search_news, query)

    async def search_wikipedia(query: str) -> Any:
        return await run_blocking_tool(wikipedia.search_wikipedia, query)

    async def get_current_stock_price(symbol: str) -> Any:
        return await run_blocking_tool(finance.get_current_stock_price, symbol)

    async def get_company_info(symbol: str) -> Any:
        return await run_blocking_tool(finance.get_company_info, symbol)

    async def get_top_hackernews_stories(num_stories: int = 5) -> Any:
        return await run_blocking_tool(hacker_news.get_top_hackernews_stories, max(1, min(int(num_stories), 10)))

    async def read(url: str) -> Any:
        return await read_article(url)

    query = {"query": string("What to search for")}
    return [
        explicit_tool("web_search", "Search the web for current information.", web_search, query, ["query"]),
        explicit_tool("search_news", "Search recent news stories.", search_news, query, ["query"]),
        explicit_tool(
            "read_article",
            "Read a public web article from a URL, e.g. one from a search result.",
            read,
            {"url": string("The article's http or https URL")},
            ["url"],
        ),
        explicit_tool(
            "search_wikipedia", "Look up background facts on Wikipedia.", search_wikipedia, query, ["query"]
        ),
        explicit_tool(
            "get_current_stock_price", "Get a stock's current price.", get_current_stock_price, symbol, ["symbol"]
        ),
        explicit_tool(
            "get_company_info", "Get a public company's profile and key figures.", get_company_info, symbol, ["symbol"]
        ),
        explicit_tool(
            "get_top_hackernews_stories",
            "Get the top stories on Hacker News.",
            get_top_hackernews_stories,
            {"num_stories": {"type": "integer", "minimum": 1, "maximum": 10}},
        ),
    ]
