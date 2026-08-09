from unittest.mock import AsyncMock

import pytest

from mediaforge.config import get_settings
from mediaforge.storage import MinioStorage


@pytest.mark.asyncio
async def test_asset_and_upload_keys_are_namespaced(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "minio_endpoint_url": "http://minio:9000",
            "minio_bucket": "mediaforge",
            "minio_access_key": "test",
            "minio_secret_key": "test-secret",
            "minio_public_base_url": "http://localhost:9000/mediaforge",
        }
    )
    storage = MinioStorage(settings)
    put = AsyncMock(side_effect=lambda key, data, ext: storage._public_url(key))
    monkeypatch.setattr(storage, "_put", put)

    asset_url = await storage.save_asset("t-1", "job-1", "asset-1", b"image", "png")
    upload_url = await storage.save_upload("t-1", "upload-1", b"image", ".jpg")

    assert asset_url.endswith("/assets/t-1/job-1/asset-1.png")
    assert upload_url.endswith("/uploads/t-1/upload-1.jpg")
