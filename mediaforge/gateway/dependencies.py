"""FastAPI dependency injection helpers for identity resolution.

`get_current_principal` is the single auth gate used by every protected
router. Resolution order:

  1. access-token cookie (primary, set by /api/v1/auth/login)
  2. Authorization: Bearer <token> header (OAuth-style callers)
  3. X-Api-Key header — only accepted when backcompat_demo_keys is True or
     a real DB-backed api_key exists

For JWT paths, after signature verification:
  a. Check the JTI blacklist (populated on logout) — reject if found.
  b. Read session cache from Redis (populated on login/refresh) — return
     cached (User, Tenant) without a DB round-trip on cache hit.
  c. Fall through to DB lookup on cache miss.

On success it returns a (User, Tenant) tuple. On failure it raises a
401 HTTPException with a `code` field so the frontend can distinguish
"expired" (auto-refresh) from "invalid" (force logout).
"""

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request
from loguru import logger

from mediaforge.auth.jwt import (
    TokenExpiredError,
    TokenError,
    verify_access_token,
)
from mediaforge.auth.session_cache import get_cached_session, is_blacklisted
from mediaforge.auth.tenant import TenantResolver
from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.redis_client import get_redis
from mediaforge.models.tenant import Tenant, TenantPlan, TenantQuota
from mediaforge.models.user import User


def _dict_to_user(d: dict) -> User:
    import uuid
    return User(
        user_id=uuid.UUID(d["user_id"]),
        tenant_id=uuid.UUID(d["tenant_id"]),
        email=d["email"],
        display_name=d.get("display_name"),
        status=d.get("status", "active"),
    )


def _dict_to_tenant(d: dict) -> Tenant:
    import uuid
    plan = TenantPlan(d.get("plan", "starter"))
    quotas_raw = d.get("quotas")
    if isinstance(quotas_raw, dict):
        quotas = TenantQuota(plan=plan, **{k: v for k, v in quotas_raw.items() if k != "plan"})
    else:
        quotas = TenantQuota(plan=plan)
    return Tenant(
        tenant_id=uuid.UUID(d["tenant_id"]),
        name=d.get("name", ""),
        api_key_hash=d.get("api_key_hash", ""),
        plan=plan,
        quotas=quotas,
    )


async def get_current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> tuple[User, Tenant]:
    resolver = TenantResolver()

    from mediaforge.config import get_settings
    s = get_settings()
    token = request.cookies.get(s.cookie_access_name)
    source = "cookie"

    # Bearer header fallback
    if not token and authorization:
        scheme, _, bearer = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer:
            raise HTTPException(status_code=401, detail={"code": "invalid_token", "msg": "Bad Authorization header"})
        token = bearer
        source = "bearer"

    if token:
        try:
            payload = verify_access_token(token)
        except TokenExpiredError:
            raise HTTPException(status_code=401, detail={"code": "token_expired", "msg": "Access token expired"})
        except TokenError:
            raise HTTPException(status_code=401, detail={"code": "invalid_token", "msg": f"Invalid {source} token"})

        jti = payload.get("jti", "")

        # a. JTI blacklist check — logout invalidates the token immediately
        if jti and await is_blacklisted(jti):
            raise HTTPException(status_code=401, detail={"code": "token_revoked", "msg": "Token has been revoked"})

        # b. Redis session cache — skip DB on hit
        if jti:
            cached = await get_cached_session(jti)
            if cached is not None:
                user_dict, tenant_dict = cached
                try:
                    return _dict_to_user(user_dict), _dict_to_tenant(tenant_dict)
                except Exception as exc:
                    logger.warning("Session cache deserialisation failed, falling through to DB: {}", exc)

        # c. DB lookup (cache miss or no jti)
        try:
            return await resolver.resolve_by_jwt(payload["sub"], payload["tid"])
        except ValueError as exc:
            raise HTTPException(status_code=401, detail={"code": "invalid_principal", "msg": str(exc)}) from exc

    # Legacy API key (dev / real DB-backed key)
    if api_key:
        try:
            return await resolver.resolve_by_api_key(api_key)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail={"code": "invalid_api_key", "msg": str(exc)}) from exc

    raise HTTPException(status_code=401, detail={"code": "missing_credentials", "msg": "No cookie, bearer, or API key"})


async def get_tenant_only(
    principal: tuple[User, Tenant] = Depends(get_current_principal),
) -> Tenant:
    return principal[1]


async def get_current_user(
    principal: tuple[User, Tenant] = Depends(get_current_principal),
) -> User:
    return principal[0]


async def get_job_store() -> JobStore:
    return JobStore(get_engine(), await get_redis())


async def get_redis_client() -> Any:
    from mediaforge.db import redis_client as redis_module
    return await redis_module.get_redis()
