import asyncio
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, Field

from mediaforge.config import get_settings
from mediaforge.orchestrator.agent_tools import (
    CheckImageComplianceTool,
    GetGenerationJobTool,
    SubmitGenerationJobTool,
)
from mediaforge.orchestrator.rag_tool import RAGSearchTool
from mediaforge.rag.factory import get_vector_store

_saver = None
_pool = None
_saver_lock = asyncio.Lock()
_saver_backend = "uninitialized"


class AgentResponse(BaseModel):
    intent: Literal[
        "help",
        "reference_search",
        "generation",
        "quality_repair",
        "task_query",
        "conversation_fallback",
    ] = Field(default="conversation_fallback", description="本轮用户意图")
    status: Literal[
        "answered", "need_input", "tool_error", "confirmation_required"
    ] = Field(description="当前回答状态")
    answer: str = Field(description="直接展示给用户的简洁中文回答")
    evidence: list[str] = Field(
        default_factory=list,
        description="本轮回答实际依据的业务工具名称；没有调用工具时为空",
    )


async def _postgres_available(dsn: str) -> bool:
    try:
        import psycopg

        async with await psycopg.AsyncConnection.connect(
            dsn,
            autocommit=True,
            connect_timeout=10,
            gssencmode="disable",
        ) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


async def _get_saver():
    global _saver, _pool, _saver_backend
    if _saver is not None:
        return _saver
    async with _saver_lock:
        if _saver is not None:
            return _saver

        dsn = get_settings().database_url.replace("+asyncpg://", "://", 1)
        if await _postgres_available(dsn):
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            pool = AsyncConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=10,
                timeout=60,
                max_idle=300,
                kwargs={
                    "autocommit": True,
                    "row_factory": dict_row,
                    "prepare_threshold": 0,
                    "connect_timeout": 15,
                    "gssencmode": "disable",
                },
                open=False,
            )
            try:
                await pool.open()
                from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

                saver = AsyncPostgresSaver(
                    conn=pool,
                    serde=JsonPlusSerializer(allowed_msgpack_modules=[AgentResponse]),
                )
                await saver.setup()
                _pool = pool
                _saver = saver
                _saver_backend = "postgres"
                return saver
            except Exception:
                await pool.close()

        settings = get_settings()
        if settings.app_env.lower() == "production":
            _saver_backend = "error"
            raise RuntimeError("PostgreSQL checkpointer is required in production")

        from langgraph.checkpoint.memory import MemorySaver
        from loguru import logger

        logger.warning("Using MemorySaver; chat history will not persist across restarts")
        _saver = MemorySaver()
        _saver_backend = "memory"
        return _saver


def get_checkpointer_status() -> str:
    return _saver_backend


async def initialize_checkpointer() -> None:
    from mediaforge.orchestrator.agent_prompt import get_prompt

    get_prompt(get_settings().agent_prompt_version)
    await _get_saver()


async def close_checkpointer() -> None:
    global _saver, _pool, _saver_backend
    if _pool is not None:
        await _pool.close()
    _saver = None
    _pool = None
    _saver_backend = "uninitialized"


async def build_supervisor_graph(
    llm=None,
    tenant_id: str = "",
    user_id: str = "",
    session_id: str = "default",
    allowed_tool_names: frozenset[str] | None = None,
):
    """Build one bounded tool-using agent; generation actions become durable jobs."""
    settings = get_settings()
    if llm is None:
        from langchain_openai import ChatOpenAI

        fallback_models = None
        if settings.agent_fallback_model and settings.agent_fallback_model != settings.agent_model:
            fallback_models = [settings.agent_model, settings.agent_fallback_model]
        llm = ChatOpenAI(
            model=settings.agent_model,
            openai_api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            openai_proxy=settings.http_proxy or None,
            max_tokens=settings.agent_max_output_tokens,
            temperature=settings.agent_temperature,
            extra_body={"models": fallback_models} if fallback_models else None,
        )

    redis = None
    try:
        from mediaforge.db.redis_client import get_redis

        redis = await get_redis()
    except Exception:
        pass

    enabled = (
        frozenset(
            {"rag_search", "submit_generation_job", "check_image_compliance", "get_generation_job"}
        )
        if allowed_tool_names is None
        else allowed_tool_names
    )
    tools = []
    if "rag_search" in enabled:
        try:
            vector_store = get_vector_store()
        except Exception:
            vector_store = None
        tools.append(
            RAGSearchTool(
                vector_store,
                redis=redis,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
        )
    if "submit_generation_job" in enabled:
        tools.append(
            SubmitGenerationJobTool(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
        )
    if "check_image_compliance" in enabled:
        tools.append(CheckImageComplianceTool(tenant_id=tenant_id))
    if "get_generation_job" in enabled:
        tools.append(GetGenerationJobTool(tenant_id=tenant_id))
    from mediaforge.orchestrator.agent_prompt import SUMMARY_PROMPT, get_prompt

    _, _, system_prompt = get_prompt(settings.agent_prompt_version)

    return create_agent(
        llm,
        tools=tools,
        system_prompt=system_prompt,
        response_format=ToolStrategy(
            AgentResponse,
            tool_message_content="最终回答已按结构化格式生成",
        ),
        middleware=[
            SummarizationMiddleware(
                llm,
                trigger=("messages", settings.agent_summary_trigger_messages),
                keep=("messages", settings.agent_summary_keep_messages),
                summary_prompt=SUMMARY_PROMPT,
            )
        ],
        checkpointer=await _get_saver(),
        name="mediaforge_agent",
    )
