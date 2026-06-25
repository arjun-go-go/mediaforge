"""Global httpx.AsyncClient singletons for connection reuse.

Creating a new httpx.AsyncClient per request wastes 100-500ms on DNS + TCP +
TLS handshake. A shared client keeps connections alive and amortizes setup.

Usage:
    from mediaforge.http_clients import get_openrouter_client, close_clients

    client = await get_openrouter_client()
    resp = await client.post(...)  # reuses pooled connection
"""

import asyncio

import httpx

from mediaforge.config import get_settings

_openrouter_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_openrouter_client() -> httpx.AsyncClient:
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client
    async with _client_lock:
        if _openrouter_client is None:
            s = get_settings()
            _openrouter_client = httpx.AsyncClient(
                timeout=180.0,
                proxy=s.http_proxy or None,
                limits=httpx.Limits(
                    max_connections=200,
                    max_keepalive_connections=50,
                    keepalive_expiry=120,
                ),
                http2=True,
            )
    return _openrouter_client


async def close_clients() -> None:
    global _openrouter_client
    if _openrouter_client is not None:
        await _openrouter_client.aclose()
        _openrouter_client = None
