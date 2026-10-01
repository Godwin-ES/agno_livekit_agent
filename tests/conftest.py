from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest


@pytest.fixture
def client_factory() -> Callable[[httpx.MockTransport], httpx.AsyncClient]:
    clients: list[httpx.AsyncClient] = []

    def create(transport: httpx.MockTransport) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=transport, timeout=4.0)
        clients.append(client)
        return client

    yield create

    for client in clients:
        if not client.is_closed:
            # pytest-asyncio is intentionally not required by this synchronous fixture.
            import asyncio

            asyncio.run(client.aclose())
