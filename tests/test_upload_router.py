import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config  # noqa: E402

mediaforge.config.clear_settings_cache()

from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from mediaforge.config import get_settings  # noqa: E402
from mediaforge.gateway.main import app  # noqa: E402


def _disk_path_from_url(url: str, tenant_id: str) -> Path:
    filename = Path(url).name
    return Path(get_settings().output_dir) / "uploads" / tenant_id / filename


def _extract_tenant_id_from_url(url: str) -> str:
    # URL shape: <prefix>/uploads/<tenant_id>/<filename>
    parts = url.split("/")
    uploads_idx = parts.index("uploads")
    return parts[uploads_idx + 1]


def test_upload_image_returns_url():
    client = TestClient(app)
    url = None
    tenant_id = None
    try:
        response = client.post(
            "/api/v1/upload",
            headers={"X-Api-Key": "demo-key-pro"},
            files={"file": ("test.jpg", b"fake-image-bytes", "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        url = data["url"]

        prefix = get_settings().upload_url_prefix
        assert url.startswith(f"{prefix}/uploads/")
        assert url.endswith(".jpg")

        tenant_id = _extract_tenant_id_from_url(url)
        assert tenant_id  # non-empty UUID segment

        dest = _disk_path_from_url(url, tenant_id)
        assert dest.exists()
        assert dest.read_bytes() == b"fake-image-bytes"
    finally:
        if url and tenant_id:
            _disk_path_from_url(url, tenant_id).unlink(missing_ok=True)
            upload_dir = Path(get_settings().output_dir) / "uploads" / tenant_id
            if upload_dir.exists() and not any(upload_dir.iterdir()):
                upload_dir.rmdir()


def test_upload_missing_api_key_returns_401():
    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        files={"file": ("test.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 401
