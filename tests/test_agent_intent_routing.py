import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from mediaforge.orchestrator.agent_intent import classify_agent_intent, help_response, tools_for_intent
from mediaforge.orchestrator.rag_tool import RAGSearchTool
from mediaforge.rag.models import RagResult
from mediaforge.models.tenant import Tenant, TenantPlan
from mediaforge.models.user import User


@pytest.mark.parametrize(
    ("message", "intent", "execute_business_tool"),
    [
        ("怎么检索爆款商品", "help", False),
        ("帮我找浅蓝色休闲牛仔裤相似爆款", "reference_search", True),
        ("这张图符合 Amazon 主图要求吗", "quality_repair", True),
        ("检查这段营销提示词是否合规", "help", False),
        ("用这张图生成淘宝主图", "generation", True),
        ("任务完成了吗", "task_query", True),
        ("项目使用哪些图片模型", "help", False),
    ],
)
def test_agent_intent_classification(message, intent, execute_business_tool):
    route = classify_agent_intent(message)
    assert route.intent == intent
    assert route.execute_business_tool is execute_business_tool


def test_search_help_returns_usage_instead_of_fake_results():
    response = help_response("怎么检索爆款商品")
    assert "选择商品" in response or "上传" in response
    assert "检索条件" in response
    assert "未找到" not in response


def test_core_intents_only_receive_required_tools():
    assert tools_for_intent("reference_search") == {"rag_search"}
    assert tools_for_intent("generation") == {"rag_search", "submit_generation_job"}
    assert tools_for_intent("quality_repair") == {"get_generation_job", "check_image_compliance"}
    assert tools_for_intent("task_query") == {"get_generation_job"}
    assert tools_for_intent("help") == set()
    assert tools_for_intent("conversation_fallback") == set()


class CountingRetriever:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = 0

    async def retrieve(self, **kwargs):
        self.calls += 1
        return self.results


@pytest.mark.asyncio
async def test_generic_rag_query_is_rejected_before_retrieval():
    retriever = CountingRetriever()
    tool = RAGSearchTool(vector_store=None)
    tool.retriever = retriever
    tool.embed_client = None
    result = json.loads(await tool._arun(query_text="爆款商品"))
    assert result["ok"] is False
    assert result["error_code"] == "SEARCH_CONTEXT_REQUIRED"
    assert retriever.calls == 0


@pytest.mark.asyncio
async def test_low_confidence_rag_results_are_not_exposed(monkeypatch):
    monkeypatch.setattr(
        "mediaforge.config.get_settings",
        lambda: SimpleNamespace(agent_rag_min_score=0.25),
    )
    retriever = CountingRetriever(
        [RagResult(product_id="LOW", score=0.1, metadata={"image_url": "https://example.com/low.jpg"})]
    )
    tool = RAGSearchTool(vector_store=None)
    tool.retriever = retriever
    tool.embed_client = None
    result = json.loads(await tool._arun(query_text="浅蓝色休闲牛仔裤"))
    assert result["matched"] is False
    assert "results" not in result
    assert "fallback_results" not in result
    assert "LOW" not in json.dumps(result)
    assert "low.jpg" not in json.dumps(result)


class RerankEmbedClient:
    async def embed_text(self, text):
        return [0.1]

    async def embed_image(self, image_path):
        return [0.2]

    async def rerank(self, query_text, query_image_path, candidates, top_n):
        return [
            {**candidates[1], "rerank_score": 0.91},
            {**candidates[0], "rerank_score": 0.52},
        ]


@pytest.mark.asyncio
async def test_agent_rag_filters_on_vl_rerank_score(monkeypatch):
    monkeypatch.setattr(
        "mediaforge.config.get_settings",
        lambda: SimpleNamespace(agent_rag_min_score=0.25),
    )
    retriever = CountingRetriever(
        [
            RagResult(product_id="SKU033", score=0.0302, image_url="https://example.com/33.jpg", metadata={"category": "wide_leg_jeans"}),
            RagResult(product_id="SKU012", score=0.0295, image_url="https://example.com/12.jpg", metadata={"category": "wide_leg_jeans"}),
        ]
    )
    tool = RAGSearchTool(vector_store=None)
    tool.retriever = retriever
    tool.embed_client = RerankEmbedClient()

    result = json.loads(
        await tool._arun(
            query_text="查找相似爆款牛仔裤",
            image_path="https://example.com/query.jpg",
        )
    )

    assert result["matched"] is True
    assert result["score_type"] == "vl_rerank"
    assert result["results"][0]["product_id"] == "SKU012"
    assert result["results"][0]["score"] == 0.91


@pytest.mark.asyncio
async def test_help_chat_direct_response_is_in_chat_scope(monkeypatch):
    from mediaforge.gateway.routers import agent
    from mediaforge.gateway.main import app

    class FakeGraph:
        def __init__(self):
            self.updates = []

        async def aupdate_state(self, config, values):
            self.updates.append((config, values))

    graph = FakeGraph()
    monkeypatch.setattr(agent, "_acquire_tenant_slot", AsyncMock(return_value=True))
    monkeypatch.setattr(agent, "_release_tenant_slot", AsyncMock())
    monkeypatch.setattr(agent, "_get_graph", AsyncMock(return_value=graph))
    monkeypatch.setattr(agent, "_touch_agent_session", AsyncMock())
    monkeypatch.setattr(agent, "_trusted_message", AsyncMock(return_value="怎么检索爆款商品"))
    monkeypatch.setattr(agent, "CostTracker", lambda: SimpleNamespace(record=AsyncMock()))
    monkeypatch.setattr("mediaforge.db.audit_store.audit", AsyncMock())

    tenant_id = uuid.uuid4()
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email="user@example.com")
    tenant = Tenant(tenant_id=tenant_id, name="Test", plan=TenantPlan.pro)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/agent/chat",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "app": app,
        },
        receive=receive,
    )
    request.state.trace_id = str(uuid.uuid4())

    response = await agent.chat(
        request,
        agent.AgentChatPayload(message="怎么检索爆款商品", session_id="regression"),
        (user, tenant),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    assert '"intent": "help"' in body
    assert '"status": "answered"' in body
    assert "rag_search" not in body
    assert len(graph.updates) == 1
