"""Global httpx.AsyncClient singletons for connection reuse.

Creating a new httpx.AsyncClient per request wastes 100-500ms on DNS + TCP +
TLS handshake. A shared client keeps connections alive and amortizes setup.

The client is cached per running event loop. Celery workers call asyncio.run()
once per task, which creates and tears down a fresh loop; reusing a client
bound to a closed loop raises "Event loop is closed". Keying the cache by
loop id ensures each loop gets its own client.

Usage:
    from mediaforge.http_clients import get_openrouter_client, close_clients

    client = await get_openrouter_client()
    resp = await client.post(...)  # reuses pooled connection
"""

import asyncio

import httpx

from mediaforge.config import get_settings

_clients: dict[int, httpx.AsyncClient] = {}
_client_lock = asyncio.Lock()


def _build_client() -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(
        timeout=180.0,
        proxy=s.http_proxy or None,
        limits=httpx.Limits(
            max_connections=200,
            max_keepalive_connections=50,
            keepalive_expiry=120,
        ),
        http2=True,
    )


async def get_openrouter_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    key = id(loop)
    client = _clients.get(key)
    if client is not None and not client.is_closed:
        return client
    async with _client_lock:
        client = _clients.get(key)
        if client is None or client.is_closed:
            _clients[key] = _build_client()
    return _clients[key]


async def close_clients() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = id(loop)
    client = _clients.pop(key, None)
    if client is not None and not client.is_closed:
        await client.aclose()
