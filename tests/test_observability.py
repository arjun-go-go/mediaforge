import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from mediaforge.gateway.main import app
from mediaforge.gateway.dependencies import get_job_store, get_redis_client


def test_batch_response_includes_trace_headers():
    mock_store = AsyncMock()
    mock_store.create_job.return_value = "job-test-123"
    mock_store.start_job.return_value = None
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=1)
    app.dependency_overrides[get_job_store] = lambda: mock_store
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/batch/submit",
            headers={"X-Api-Key": "demo-key-pro"},
            json={
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
                ]
            },
        )
        assert response.status_code == 202
        assert "x-trace-id" in response.headers
        assert "x-langsmith-project" in response.headers
    finally:
        app.dependency_overrides.clear()
