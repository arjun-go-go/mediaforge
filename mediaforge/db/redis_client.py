import asyncio
import json

import redis.asyncio as redis

from mediaforge.config import get_settings

_redis: redis.Redis | None = None
_redis_lock = asyncio.Lock()


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is not None:
        return _redis
    async with _redis_lock:
        if _redis is None:
            _redis = await redis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                max_connections=100,
                socket_timeout=10,
                socket_connect_timeout=5,
                health_check_interval=30,
            )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def publish_event(channel: str, event: dict) -> None:
    r = await get_redis()
    await r.publish(channel, json.dumps(event))
