import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config

mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_get_me_returns_tenant_info_via_demo_key():
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"X-Api-Key": "demo-key-pro"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Pro"
    assert data["plan"] == "pro"
    assert "max_concurrent_jobs" in data["quotas"]
    # tenant_id is now a UUID string
    assert len(data["tenant_id"]) == 36


def test_get_me_missing_key_returns_401():
    client = TestClient(app)
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_get_me_invalid_key_returns_401():
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"X-Api-Key": "not-a-valid-key"})
    assert response.status_code == 401


def test_get_me_invalid_jwt_returns_401():
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_tenants_me_alias_works():
    client = TestClient(app)
    response = client.get("/api/v1/tenants/me", headers={"X-Api-Key": "demo-key-starter"})
    assert response.status_code == 200
    data = response.json()
    assert data["plan"] == "starter"


def test_auth_me_requires_credentials():
    client = TestClient(app)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
