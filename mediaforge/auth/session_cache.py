"""Redis-backed session cache + access token blacklist.

Two concerns handled here:

1. Session cache  (key: session:{jti})
   After login/refresh, `(user_dict, tenant_dict)` is stored with a TTL
   equal to the access token lifetime.  `get_current_principal` reads this
   cache first, skipping a DB round-trip on every request.

2. JTI blacklist  (key: blacklist:{jti})
   On logout, the access token's `jti` is added to a Redis set with the
   same TTL as the original token.  `verify_access_token` (via dependency)
   checks the blacklist and rejects the token immediately even though the
   JWT signature is still valid.
"""

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from mediaforge.db.redis_client import get_redis

_SESSION_PREFIX = "session:"
_BLACKLIST_PREFIX = "blacklist:"


def _session_key(jti: str) -> str:
    return f"{_SESSION_PREFIX}{jti}"


def _blacklist_key(jti: str) -> str:
    return f"{_BLACKLIST_PREFIX}{jti}"


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------

async def cache_session(jti: str, user: Any, tenant: Any, ttl_seconds: int) -> None:
    """Store user + tenant under session:{jti} with a TTL."""
    try:
        r = await get_redis()
        payload = json.dumps({
            "user": _model_to_dict(user),
            "tenant": _model_to_dict(tenant),
        })
        await r.setex(_session_key(jti), ttl_seconds, payload)
    except Exception as exc:
        logger.warning("Session cache write failed (non-fatal): jti={} err={}", jti, exc)


async def get_cached_session(jti: str) -> tuple[dict, dict] | None:
    """Return (user_dict, tenant_dict) from cache, or None on miss/error."""
    try:
        r = await get_redis()
        raw = await r.get(_session_key(jti))
        if raw is None:
            return None
        data = json.loads(raw)
        return data["user"], data["tenant"]
    except Exception as exc:
        logger.warning("Session cache read failed (non-fatal): jti={} err={}", jti, exc)
        return None


async def invalidate_session(jti: str) -> None:
    """Remove the session cache entry (called on logout)."""
    try:
        r = await get_redis()
        await r.delete(_session_key(jti))
    except Exception as exc:
        logger.warning("Session cache delete failed (non-fatal): jti={} err={}", jti, exc)


# ---------------------------------------------------------------------------
# JTI blacklist
# ---------------------------------------------------------------------------

async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """Add jti to the blacklist so it cannot be used even if the JWT is valid."""
    try:
        r = await get_redis()
        await r.setex(_blacklist_key(jti), ttl_seconds, "1")
    except Exception as exc:
        logger.warning("JTI blacklist write failed (non-fatal): jti={} err={}", jti, exc)


async def is_blacklisted(jti: str) -> bool:
    """Return True if the jti is in the blacklist."""
    try:
        r = await get_redis()
        return await r.exists(_blacklist_key(jti)) == 1
    except Exception as exc:
        logger.warning("JTI blacklist check failed (non-fatal): jti={} err={}", jti, exc)
        return False  # fail-open: don't block requests on Redis errors


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _model_to_dict(obj: Any) -> dict:
    """Convert Pydantic model or plain dict to a JSON-serialisable dict."""
    if hasattr(obj, "model_dump"):
        raw = obj.model_dump()
    elif hasattr(obj, "dict"):
        raw = obj.dict()
    else:
        raw = dict(obj)

    # Convert UUID / datetime values to strings for JSON serialisation.
    result = {}
    for k, v in raw.items():
        if v is None:
            result[k] = None
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = str(v) if not isinstance(v, (int, float, bool, str, list, dict)) else v
    return result
