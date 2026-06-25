import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config; mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_agent_chat_without_auth():
    client = TestClient(app)
    response = client.post("/api/v1/agent/chat", json={"message": "hello"})
    assert response.status_code == 401
