import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mediaforge.orchestrator.agent_prompt import SYSTEM_PROMPT
from mediaforge.orchestrator.agent_tools import SubmitGenerationJobTool
from mediaforge.db.tables import ProductTable


class FakeRedis:
    def __init__(self):
        self.values: dict[str, tuple[int, str]] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = (ttl, value)


@pytest.mark.asyncio
async def test_agent_prepares_confirmation_without_creating_job(monkeypatch, db_engine):
    redis = FakeRedis()
    monkeypatch.setattr("mediaforge.db.redis_client.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("mediaforge.db.audit_store.audit", AsyncMock())
    monkeypatch.setattr("mediaforge.db.engine.get_engine", lambda: db_engine)

    tenant_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    async with db_engine.begin() as connection:
        await connection.execute(
            ProductTable.__table__.insert().values(
                document_id="private:SKU001",
                tenant_id=tenant_id,
                sku_code="SKU001",
                visibility="private",
                source_type="user_upload",
                category="trusted-apparel",
                image_url="https://minio.example/mediaforge/rag/products/private/SKU001.jpg",
            )
        )

    tool = SubmitGenerationJobTool(
        tenant_id=str(tenant_id),
        user_id="22222222-2222-2222-2222-222222222222",
        session_id="session-a",
    )
    missing_platform = json.loads(
        await tool._arun(
            sku_id="SKU001",
            product_image_url="https://example.com/product.jpg",
            product_name="Blue shirt",
            category="apparel",
            output_types=["main_image"],
        )
    )
    assert missing_platform["error_code"] == "TARGET_PLATFORM_REQUIRED"

    result = json.loads(
        await tool._arun(
            sku_id="SKU001",
            product_image_url="https://example.com/product.jpg",
            product_name="Blue shirt",
            category="apparel",
            target_platforms=["amazon"],
            output_types=["main_image"],
        )
    )

    assert result["status"] == "confirmation_required"
    assert result.get("job_id") is None
    assert len(redis.values) == 1
    key, (ttl, raw) = next(iter(redis.values.items()))
    assert ":11111111-1111-1111-1111-111111111111:" in key
    assert ":22222222-2222-2222-2222-222222222222:" in key
    assert ttl > 0
    saved_sku = json.loads(raw)["payload"]["skus"][0]
    assert saved_sku["sku_id"] == "SKU001"
    assert saved_sku["product_image_url"].endswith("/SKU001.jpg")
    assert saved_sku["category"] == "trusted-apparel"
    assert json.loads(raw)["agent_release"]["prompt_version"] == "2026-08-07.8"


def test_agent_prompt_requires_explicit_confirmation():
    assert "确认并提交" in SYSTEM_PROMPT
    assert "不会立即产生费用" in SYSTEM_PROMPT
    assert "不能绕过确认流程" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_production_rejects_memory_checkpointer(monkeypatch):
    from mediaforge.orchestrator import agent_graph

    monkeypatch.setattr(agent_graph, "_saver", None)
    monkeypatch.setattr(agent_graph, "_pool", None)
    monkeypatch.setattr(agent_graph, "_saver_backend", "uninitialized")
    monkeypatch.setattr(agent_graph, "_postgres_available", AsyncMock(return_value=False))
    monkeypatch.setattr(
        agent_graph,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://invalid/invalid",
            app_env="production",
        ),
    )

    with pytest.raises(RuntimeError, match="required in production"):
        await agent_graph._get_saver()
    assert agent_graph.get_checkpointer_status() == "error"
