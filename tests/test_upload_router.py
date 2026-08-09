import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config  # noqa: E402

mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient  # noqa: E402

from mediaforge.gateway.main import app  # noqa: E402


def test_upload_image_returns_minio_url(monkeypatch):
    storage = MagicMock()
    storage.save_upload = AsyncMock(
        return_value="http://localhost:9000/mediaforge/uploads/tenant/upload.jpg"
    )
    monkeypatch.setattr("mediaforge.gateway.routers.upload.get_storage", lambda: storage)

    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        headers={"X-Api-Key": "test-api-key-pro"},
        files={"file": ("test.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["url"].startswith("http://localhost:9000/mediaforge/uploads/")
    storage.save_upload.assert_awaited_once()


def test_upload_missing_api_key_returns_401():
    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        files={"file": ("test.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 401
