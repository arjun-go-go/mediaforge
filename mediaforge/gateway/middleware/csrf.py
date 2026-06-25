"""CSRF protection middleware (Double-Submit Cookie).

The server issues a `mf_csrf` cookie alongside the auth cookies. The
cookie is readable by JavaScript (httponly=False) so the frontend can
echo it back in a custom header on every state-changing request.

Safety:
  * GET / HEAD / OPTIONS are always allowed (side-effect-free by convention).
  * Requests without an auth cookie are skipped (unauthenticated callers
    have no session to CSRF-attack).
  * The login and signup endpoints are exempt.

Comparison uses hmac.compare_digest for timing-attack resistance.
"""

import hmac
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from mediaforge.config import get_settings

_EXEMPT_PATHS: set[str] = {"/api/v1/auth/login", "/api/v1/auth/signup", "/api/v1/auth/refresh"}
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        s = get_settings()
        cookie_token = request.cookies.get(s.cookie_csrf_name)
        if not cookie_token:
            # No CSRF cookie ⇒ caller is not in an authenticated session.
            # Skip (the auth layer will 401 first anyway).
            return await call_next(request)

        header_token = request.headers.get(s.csrf_header_name)
        if not header_token or not hmac.compare_digest(cookie_token, header_token):
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "csrf_failed", "msg": "CSRF token missing or invalid"}},
            )
        return await call_next(request)
