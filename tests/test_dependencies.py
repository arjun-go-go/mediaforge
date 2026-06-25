import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import mediaforge.config

mediaforge.config.clear_settings_cache()

import pytest
from fastapi import HTTPException

from mediaforge.gateway.dependencies import get_current_principal


class _FakeRequest:
    """Minimal Request-like object sufficient for the dependency."""

    def __init__(self, *, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}

    def url_for(self, *_a, **_kw):  # pragma: no cover - not used
        return ""


@pytest.mark.asyncio
async def test_missing_credentials_raises_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_principal(_FakeRequest())
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "missing_credentials"


@pytest.mark.asyncio
async def test_invalid_bearer_scheme_raises_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_principal(
            _FakeRequest(),
            authorization="Basic dXNlcjpwYXNz",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_invalid_api_key_raises_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_principal(
            _FakeRequest(),
            api_key="not-a-real-key",
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_demo_api_key_resolves_when_backcompat_enabled():
    """When backcompat_demo_keys=true (test env default), demo keys resolve."""
    from mediaforge.config import get_settings

    if not get_settings().backcompat_demo_keys:
        pytest.skip("backcompat_demo_keys disabled")

    user, tenant = await get_current_principal(
        _FakeRequest(),
        api_key="demo-key-pro",
    )
    assert tenant.plan == "pro"
    assert user is not None
