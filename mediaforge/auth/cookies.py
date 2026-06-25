"""Auth cookie helpers.

Three cookies are managed:
  * access  — short-lived JWT, HttpOnly
  * refresh — long-lived JWT, HttpOnly
  * csrf    — random token, readable by JS (NOT HttpOnly) for double-submit

All cookies share Secure / SameSite / Domain settings from `Settings`.
`path="/"` so they're sent on every API request.
"""

from fastapi import Response

from mediaforge.config import get_settings


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    s = get_settings()
    access_max_age = s.jwt_access_expires_seconds
    refresh_max_age = s.jwt_refresh_expires_seconds
    common = {
        "secure": s.cookie_secure,
        "samesite": s.cookie_same_site,
        "path": "/",
    }
    if s.cookie_domain:
        common["domain"] = s.cookie_domain

    response.set_cookie(
        s.cookie_access_name,
        access_token,
        max_age=access_max_age,
        httponly=True,
        **common,
    )
    response.set_cookie(
        s.cookie_refresh_name,
        refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        **common,
    )
    response.set_cookie(
        s.cookie_csrf_name,
        csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    common = {"path": "/"}
    if s.cookie_domain:
        common["domain"] = s.cookie_domain
    for name in (s.cookie_access_name, s.cookie_refresh_name, s.cookie_csrf_name):
        response.delete_cookie(name, **common)
