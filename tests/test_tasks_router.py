import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

import mediaforge.config
mediaforge.config.clear_settings_cache()

import pytest
from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_get_task_without_auth():
    client = TestClient(app)
    response = client.get("/api/v1/tasks/123")
    assert response.status_code == 401
