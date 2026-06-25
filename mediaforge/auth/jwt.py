"""JWT access + refresh token helpers.

Access tokens are short-lived (default 15 min) and signed with jwt_secret.
Refresh tokens are long-lived (default 7 d) and signed with a separate
jwt_refresh_secret so that the two can be rotated independently.

Both tokens include `sub` (user id), `tid` (tenant id), `iat` and `jti`.
Expired access tokens raise `TokenExpiredError` so callers can return a
specific 401 code that the frontend recognises for auto-refresh.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import ExpiredSignatureError, JWTError, jwt

from mediaforge.config import get_settings


class TokenError(ValueError):
    """Base class for all token verification failures."""


class TokenExpiredError(TokenError):
    """Raised when a token's `exp` claim is in the past."""


class InvalidTokenError(TokenError):
    """Raised for signature / structure / claim failures."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: str,
    tenant_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    s = get_settings()
    expire_in = expires_delta or timedelta(seconds=s.jwt_access_expires_seconds)
    now = _now()
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "iat": now,
        "exp": now + expire_in,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    jti: str,
    expires_delta: timedelta | None = None,
) -> str:
    s = get_settings()
    expire_in = expires_delta or timedelta(seconds=s.jwt_refresh_expires_seconds)
    now = _now()
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "iat": now,
        "exp": now + expire_in,
        "jti": jti,
        "type": "refresh",
    }
    return jwt.encode(payload, s.jwt_refresh_secret, algorithm=s.jwt_algorithm)


def verify_access_token(token: str) -> dict:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token expired") from exc
    except JWTError as exc:
        raise InvalidTokenError("Invalid access token") from exc
    if payload.get("type") and payload["type"] != "access":
        raise InvalidTokenError("Wrong token type")
    if not payload.get("sub") or not payload.get("tid"):
        raise InvalidTokenError("Missing sub/tid claim")
    return payload


def verify_refresh_token(token: str) -> dict:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_refresh_secret, algorithms=[s.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Refresh token expired") from exc
    except JWTError as exc:
        raise InvalidTokenError("Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise InvalidTokenError("Wrong token type")
    if not payload.get("sub") or not payload.get("jti"):
        raise InvalidTokenError("Missing sub/jti claim")
    return payload


# Backwards-compat shim for legacy tests / callers that pass an arbitrary
# dict payload. Will be removed once the codebase fully migrates.
def verify_token(token: str) -> dict:
    return verify_access_token(token)
