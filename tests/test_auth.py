# mediaforge/tests/test_auth.py
import os
import uuid

os.environ["JWT_SECRET"] = "test-secret"
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

import pytest

from mediaforge.auth.jwt import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
    verify_token,
)
from mediaforge.auth.password import hash_password, needs_rehash, verify_password


def test_password_roundtrip():
    pw = "hunter2-very-secret"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)
    assert not needs_rehash(hashed)


def test_create_and_verify_access_token():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = create_access_token(user_id, tenant_id)
    payload = verify_access_token(token)
    assert payload["sub"] == user_id
    assert payload["tid"] == tenant_id
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "jti" in payload


def test_create_and_verify_refresh_token():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    token = create_refresh_token(user_id, tenant_id, jti)
    payload = verify_refresh_token(token)
    assert payload["sub"] == user_id
    assert payload["tid"] == tenant_id
    assert payload["jti"] == jti
    assert payload["type"] == "refresh"


def test_access_token_rejected_by_refresh_verifier():
    token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()))
    with pytest.raises(InvalidTokenError):
        verify_refresh_token(token)


def test_refresh_token_rejected_by_access_verifier():
    token = create_refresh_token(str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_verify_invalid_token_raises():
    with pytest.raises(InvalidTokenError):
        verify_access_token("not-a-token")


def test_verify_token_backwards_compat():
    """Legacy `verify_token` still works for access tokens."""
    token = create_access_token(str(uuid.uuid4()), str(uuid.uuid4()))
    payload = verify_token(token)
    assert payload["type"] == "access"


def test_expired_token_raises_expired_error():
    from datetime import timedelta
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = create_access_token(user_id, tenant_id, expires_delta=timedelta(seconds=-1))
    with pytest.raises(TokenExpiredError):
        verify_access_token(token)
