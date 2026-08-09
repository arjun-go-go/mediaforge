import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mediaforge.db.tables import ProductTable
from mediaforge.gateway.routers.agent import AgentChatPayload, _human_message_response, _trusted_message
from mediaforge.models.tenant import Tenant, TenantPlan
from mediaforge.models.user import User
from mediaforge.orchestrator.agent_graph import AgentResponse
from mediaforge.orchestrator.agent_prompt import get_prompt
from mediaforge.orchestrator.rag_tool import RAGSearchTool
from mediaforge.rag.models import RagResult


class StubAgentRetriever:
    async def retrieve(self, **kwargs):
        return [
            RagResult(product_id="LOW", score=0.24, metadata={"category": "dress"}),
            RagResult(product_id="HIGH", score=0.81, metadata={"category": "dress"}),
        ]


@pytest.mark.asyncio
async def test_agent_product_context_is_loaded_from_tenant_database(monkeypatch, db_engine):
    tenant_id = uuid.uuid4()
    async with db_engine.begin() as connection:
        await connection.execute(
            ProductTable.__table__.insert().values(
                document_id=f"{tenant_id}:SKU-TRUSTED",
                tenant_id=tenant_id,
                sku_code="SKU-TRUSTED",
                visibility="private",
                source_type="user_upload",
                category="trusted-category",
                description="trusted-description",
                image_url="https://minio.example/trusted.jpg",
            )
        )
    monkeypatch.setattr("mediaforge.db.engine.get_engine", lambda: db_engine)

    tenant = Tenant(tenant_id=tenant_id, name="Test", plan=TenantPlan.pro)
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email="user@example.com")
    message = await _trusted_message(
        AgentChatPayload(message="生成主图", product_sku="SKU-TRUSTED"),
        tenant,
        user,
    )

    assert '<business_data source="trusted_backend">' in message
    assert '"category": "trusted-category"' in message
    assert '"description": "trusted-description"' in message
    assert "https://minio.example/trusted.jpg" in message


@pytest.mark.asyncio
async def test_agent_rejects_untrusted_uploaded_image_url():
    tenant = Tenant(tenant_id=uuid.uuid4(), name="Test", plan=TenantPlan.pro)
    user = User(user_id=uuid.uuid4(), tenant_id=tenant.tenant_id, email="user@example.com")
    with pytest.raises(HTTPException, match="上传图片地址无效") as error:
        await _trusted_message(
            AgentChatPayload(
                message="生成主图",
                uploaded_image_url="https://attacker.example/product.jpg",
            ),
            tenant,
            user,
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_agent_rag_filters_results_below_minimum_score(monkeypatch):
    monkeypatch.setattr(
        "mediaforge.config.get_settings",
        lambda: SimpleNamespace(agent_rag_min_score=0.25),
    )
    tool = RAGSearchTool(vector_store=None)
    tool.retriever = StubAgentRetriever()
    tool.embed_client = None

    result = json.loads(await tool._arun(query_text="dress"))

    assert result["matched"] is True
    assert [item["product_id"] for item in result["results"]] == ["HIGH"]
    assert result["minimum_score"] == 0.25


def test_prompt_release_hash_and_rollback_version_are_deterministic():
    current_version, current_hash, _ = get_prompt("2026-08-07.6")
    previous_version, previous_hash, _ = get_prompt("2026-08-07.5")

    assert current_version == "2026-08-07.6"
    assert previous_version == "2026-08-07.5"
    assert len(current_hash) == 64
    assert current_hash != previous_hash
    with pytest.raises(ValueError, match="Unknown agent prompt version"):
        get_prompt("missing")


def test_agent_structured_response_contract():
    response = AgentResponse(
        status="tool_error",
        answer="当前无法确认",
        evidence=["get_generation_job"],
    )
    assert response.model_dump() == {
        "intent": "conversation_fallback",
        "status": "tool_error",
        "answer": "当前无法确认",
        "evidence": ["get_generation_job"],
    }


def test_agent_history_returns_uploaded_and_reference_images():
    content = (
        "生成主图\n\n<business_data source=\"trusted_backend\">\n"
        '{"uploaded_product":{"image_url":"https://minio/new.jpg","image_name":"new.jpg"},'
        '"selected_product":{"image_url":"https://minio/ref.jpg","sku_code":"SKU031","category":"jeans"},'
        '"active_source":"uploaded_product"}'
        "\n</business_data>"
    )

    response = _human_message_response(content)

    assert [item["source"] for item in response["contextImages"]] == ["upload", "product"]
    assert [item["url"] for item in response["contextImages"]] == [
        "https://minio/new.jpg",
        "https://minio/ref.jpg",
    ]
