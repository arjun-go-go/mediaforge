import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import mediaforge.config
mediaforge.config.clear_settings_cache()

import pytest
from fastapi.testclient import TestClient
from mediaforge.gateway.main import app

_VALID_SKU = {
    "sku_id": "SKU-001",
    "product_image_url": "https://example.com/img.jpg",
    "product_name": "Dress",
    "category": "apparel",
    "target_platforms": ["amazon"],
    "output_types": ["main_image"],
    "market": "US",
}


def test_submit_batch_without_auth():
    client = TestClient(app)
    response = client.post("/api/v1/batch/submit", json={"skus": [_VALID_SKU]})
    assert response.status_code == 401


def test_submit_batch_with_invalid_sku():
    client = TestClient(app)
    response = client.post(
        "/api/v1/batch/submit",
        headers={"X-Api-Key": "demo-key-pro"},
        json={
            "skus": [
                {
                    "sku_id": "",
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
    assert response.status_code == 422
