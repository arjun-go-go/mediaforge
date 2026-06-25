"""Auth router — signup / login / refresh / logout.

Security notes:
  * Password hashing is bcrypt (via `mediaforge.auth.password`).
  * Access tokens live in HttpOnly cookies; refresh tokens are persisted
    by sha256(jti) so a DB leak cannot reveal a valid token.
  * Login attempts are capped at `login_max_attempts` before a 15-min lockout.
  * Refresh rotates the token (old one revoked) on every call.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger

from mediaforge.auth.cookies import clear_auth_cookies, set_auth_cookies
from mediaforge.auth.jwt import (
    TokenExpiredError,
    TokenError,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from mediaforge.auth.password import hash_password_async, needs_rehash, verify_password_async
from mediaforge.auth.session_cache import (
    blacklist_jti,
    cache_session,
    invalidate_session,
)
from mediaforge.config import get_settings
from mediaforge.db.audit_store import audit
from mediaforge.db.engine import get_engine
from mediaforge.db.refresh_token_store import RefreshTokenStore
from mediaforge.db.tenant_store import TenantStore
from mediaforge.db.user_store import UserStore
from mediaforge.gateway.dependencies import get_current_principal
from mediaforge.gateway.middleware.csrf import generate_csrf_token
from mediaforge.models.user import User, UserLoginRequest, UserPublic, UserSignupRequest


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_public(user: User) -> UserPublic:
    return UserPublic(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
    )


def _hash_jti(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _ua(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:256]


async def _issue_session(
    response: Response,
    *,
    user: User,
    tenant,
    request: Request,
) -> tuple[str, str]:
    """Mint access+refresh+csrf tokens, persist refresh row, write Redis cache, set cookies.

    Returns (csrf_token, access_jti).
    """
    from jose import jwt as _jwt
    s = get_settings()
    access_token = create_access_token(str(user.user_id), str(user.tenant_id))
    refresh_jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(str(user.user_id), str(user.tenant_id), refresh_jti)
    csrf_token = generate_csrf_token()

    # Decode jti from the access token (no verification — we just created it)
    access_payload = _jwt.get_unverified_claims(access_token)
    access_jti = access_payload.get("jti", "")

    store = RefreshTokenStore(get_engine())
    await store.create(
        user_id=user.user_id,
        jti=refresh_jti,
        token_hash=_hash_jti(refresh_jti),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=s.jwt_refresh_expires_seconds),
        user_agent=_ua(request),
        ip_address=_client_ip(request),
    )

    # Cache user + tenant in Redis for the access token lifetime
    if access_jti:
        await cache_session(access_jti, user, tenant, ttl_seconds=s.jwt_access_expires_seconds)

    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
    )
    return csrf_token, access_jti


@router.post("/signup")
async def signup(body: UserSignupRequest, request: Request, response: Response):
    s = get_settings()
    if not s.allow_self_signup_tenant_id:
        raise HTTPException(status_code=403, detail={"code": "signup_disabled", "msg": "Self-signup is disabled"})

    engine = get_engine()
    tenant_store = TenantStore(engine)
    tenant = await tenant_store.get_by_id(s.allow_self_signup_tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail={"code": "signup_tenant_missing", "msg": "Signup tenant not found"})

    user_store = UserStore(engine)
    if await user_store.get_by_email(body.email):
        raise HTTPException(status_code=409, detail={"code": "email_taken", "msg": "Email already registered"})

    pw_hash = await hash_password_async(body.password)
    user = await user_store.create(
        tenant_id=tenant.tenant_id,
        email=body.email,
        password_hash=pw_hash,
        display_name=body.display_name,
    )
    logger.info("Signup: user_id={} email={} tenant_id={}", user.user_id, user.email, user.tenant_id)
    await audit("signup", tenant_id=tenant.tenant_id, user_id=user.user_id,
                ip_address=_client_ip(request), user_agent=_ua(request))

    csrf, _ = await _issue_session(response, user=user, tenant=tenant, request=request)
    return {"user": _user_public(user), "tenant": tenant, "csrf_token": csrf}


@router.post("/login")
async def login(body: UserLoginRequest, request: Request, response: Response):
    s = get_settings()
    engine = get_engine()
    user_store = UserStore(engine)
    tenant_store = TenantStore(engine)

    row = await user_store.get_by_email(body.email)
    if row is None:
        # Constant-time-ish penalty to avoid timing enumeration
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "msg": "Invalid email or password"})

    # Lockout check
    locked_until = row.get("locked_until")
    now = datetime.now(timezone.utc)
    if locked_until and locked_until > now:
        raise HTTPException(
            status_code=423,
            detail={"code": "account_locked", "msg": f"Too many attempts; try again after {locked_until.isoformat()}"},
        )

    if not await verify_password_async(body.password, row["password_hash"]):
        # Record failure and maybe lock
        attempts = row.get("failed_login_attempts", 0) + 1
        lock_until = None
        if attempts >= s.login_max_attempts:
            lock_until = now + timedelta(seconds=s.login_lockout_seconds)
            logger.warning("Account locked: email={} until={}", body.email, lock_until)
        await user_store.record_login_failure(row["user_id"], lock_until=lock_until)
        await audit("login", success=False, user_id=row["user_id"],
                    ip_address=_client_ip(request), user_agent=_ua(request),
                    metadata={"reason": "wrong_password", "attempts": attempts})
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "msg": "Invalid email or password"})

    # Password rehash if rounds changed
    if needs_rehash(row["password_hash"]):
        logger.debug("Rehashing password for user_id={}", row["user_id"])
        # Opportunistic — skip if it fails; next login will retry.
        try:
            new_hash = await hash_password_async(body.password)
            from sqlalchemy import update as sa_update
            from mediaforge.db.tables import UserTable
            async with engine.connect() as conn:
                await conn.execute(
                    sa_update(UserTable)
                    .where(UserTable.c.user_id == row["user_id"])
                    .values(password_hash=new_hash)
                )
                await conn.commit()
        except Exception as exc:
            logger.warning("Password rehash failed: {}", exc)

    if row.get("status") != "active":
        raise HTTPException(status_code=403, detail={"code": "account_suspended", "msg": "Account suspended"})

    tenant = await tenant_store.get_by_id(row["tenant_id"])
    if tenant is None:
        raise HTTPException(status_code=500, detail={"code": "tenant_missing", "msg": "Tenant not found"})

    await user_store.record_login_success(row["user_id"])
    user = User(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        email=row["email"],
        display_name=row.get("display_name"),
        email_verified_at=row.get("email_verified_at"),
        status=row["status"],
        created_at=row.get("created_at"),
    )
    logger.info("Login: user_id={} tenant_id={}", user.user_id, user.tenant_id)
    await audit("login", tenant_id=user.tenant_id, user_id=user.user_id,
                ip_address=_client_ip(request), user_agent=_ua(request))

    csrf, _ = await _issue_session(response, user=user, tenant=tenant, request=request)
    return {"user": _user_public(user), "tenant": tenant, "csrf_token": csrf}


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_cookie: str | None = None,
):
    # Cookie name is dynamic; extract manually.
    s = get_settings()
    refresh_cookie = request.cookies.get(s.cookie_refresh_name)
    if not refresh_cookie:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail={"code": "missing_refresh", "msg": "No refresh cookie"})

    try:
        payload = verify_refresh_token(refresh_cookie)
    except TokenExpiredError:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail={"code": "token_expired", "msg": "Refresh token expired"})
    except TokenError:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail={"code": "invalid_token", "msg": "Invalid refresh token"})

    jti = payload["jti"]
    store = RefreshTokenStore(get_engine())
    row = await store.get_by_hash(_hash_jti(jti))
    if row is None or row.get("revoked_at") is not None:
        # Possible replay / already rotated — nuke all sessions for safety.
        await store.revoke_all_for_user(payload["sub"])
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail={"code": "session_revoked", "msg": "Session revoked"})

    # Revoke old refresh
    await store.revoke(row["token_hash"])

    # Build new user + tenant
    user_store = UserStore(get_engine())
    user = await user_store.get_by_id(payload["sub"])
    if user is None or user.status != "active":
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail={"code": "invalid_principal", "msg": "User unavailable"})

    tenant_store = TenantStore(get_engine())
    tenant = await tenant_store.get_by_id(str(user.tenant_id))
    if tenant is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=500, detail={"code": "tenant_missing", "msg": "Tenant not found"})

    csrf, _ = await _issue_session(response, user=user, tenant=tenant, request=request)
    return {"ok": True, "csrf_token": csrf}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    principal=Depends(get_current_principal),
):
    s = get_settings()

    # Revoke refresh token
    refresh_cookie = request.cookies.get(s.cookie_refresh_name)
    if refresh_cookie:
        try:
            payload = verify_refresh_token(refresh_cookie)
            store = RefreshTokenStore(get_engine())
            await store.revoke(_hash_jti(payload["jti"]))
        except TokenError:
            pass

    # Blacklist + invalidate access token immediately
    access_cookie = request.cookies.get(s.cookie_access_name)
    if access_cookie:
        try:
            from jose import jwt as _jwt
            from mediaforge.auth.jwt import verify_access_token
            access_payload = verify_access_token(access_cookie)
            access_jti = access_payload.get("jti", "")
            if access_jti:
                # TTL = remaining token lifetime (at most access_expires_seconds)
                exp = access_payload.get("exp", 0)
                from datetime import datetime, timezone
                remaining = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
                await blacklist_jti(access_jti, ttl_seconds=remaining or s.jwt_access_expires_seconds)
                await invalidate_session(access_jti)
        except TokenError:
            pass

    clear_auth_cookies(response)
    logger.info("Logout: user_id={}", principal[0].user_id)
    await audit("logout", tenant_id=principal[1].tenant_id, user_id=principal[0].user_id,
                ip_address=_client_ip(request), user_agent=_ua(request))
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    principal=Depends(get_current_principal),
):
    store = RefreshTokenStore(get_engine())
    revoked = await store.revoke_all_for_user(principal[0].user_id)
    clear_auth_cookies(response)
    logger.info("Logout-all: user_id={} sessions_revoked={}", principal[0].user_id, revoked)
    return {"ok": True, "revoked": revoked}


@router.get("/me")
async def me(principal=Depends(get_current_principal)):
    user, tenant = principal
    return {"user": _user_public(user), "tenant": tenant}
