import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from mediaforge.gateway.main import app
from mediaforge.gateway.dependencies import get_job_store, get_redis_client

VALID_SKU_PAYLOAD = {
    "skus": [
        {
            "sku_id": "SKU-001",
            "product_image_url": "https://example.com/img.jpg",
            "product_name": "Dress",
            "category": "apparel",
            "target_platforms": ["amazon"],
            "output_types": ["main_image"],
            "market": "US",
        }
    ],
    "image_model": "fast",
    "video_model": "seedance",
}


def test_starter_rate_limit_blocks_after_threshold():
    mock_store = AsyncMock()
    mock_store.create_job.return_value = "job-test-123"
    mock_store.start_job.return_value = None
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=1)
    app.dependency_overrides[get_job_store] = lambda: mock_store
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    try:
        client = TestClient(app)
        response = None
        for _ in range(11):
            response = client.post(
                "/api/v1/batch/submit",
                headers={"X-Api-Key": "demo-key-starter"},
                json=VALID_SKU_PAYLOAD,
            )
        assert response.status_code == 429
    finally:
        app.dependency_overrides.clear()
