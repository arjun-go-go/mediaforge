import asyncio
from enum import Enum
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, Field

from mediaforge.config import get_settings
from mediaforge.orchestrator.agent_tools import (
    CheckComplianceTool,
    GenerateImageTool,
    GenerateVideoTool,
    StyleAnalyzerTool,
)
from mediaforge.orchestrator.rag_tool import RAGSearchTool
from mediaforge.rag.factory import get_vector_store


class ExpertAgent(str, Enum):
    IMAGE = "image_agent"
    VIDEO = "video_agent"
    COMPLIANCE = "compliance_agent"
    RAG = "rag_agent"


class Router(BaseModel):
    next: Literal["image_agent", "video_agent", "compliance_agent", "rag_agent", "FINISH"] = Field(
        description="下一步要执行的专家名称；如果用户请求已经处理完毕、无需任何专家介入，返回 FINISH。"
    )


_saver = None
_pool = None
_saver_lock = asyncio.Lock()


async def _get_saver():
    """Return a checkpointer. Prefers AsyncPostgresSaver; falls back to MemorySaver."""
    global _saver, _pool
    if _saver is not None:
        return _saver
    async with _saver_lock:
        if _saver is not None:
            return _saver
        settings = get_settings()
        dsn = settings.database_url
        if "+asyncpg://" in dsn:
            dsn = dsn.replace("+asyncpg://", "://", 1)

        if await _ping_postgres(dsn, timeout=10):
            await _drop_legacy_checkpoint_tables(dsn)

            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row

            pool = AsyncConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=10,
                timeout=60,
                max_idle=300,
                max_lifetime=3600,
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
                await asyncio.wait_for(pool.open(), timeout=30)
                saver = AsyncPostgresSaver(conn=pool)
                await asyncio.wait_for(saver.setup(), timeout=30)
                _pool = pool
                _saver = saver
                return _saver
            except Exception as exc:
                from loguru import logger
                logger.warning("AsyncPostgresSaver setup failed ({}); falling back to MemorySaver", exc)
                try:
                    await pool.close()
                except Exception:
                    pass

        from loguru import logger
        logger.warning("Using MemorySaver — chat history will not persist across restarts")
        from langgraph.checkpoint.memory import MemorySaver
        _saver = MemorySaver()
        return _saver


async def _ping_postgres(dsn: str, *, timeout: float) -> bool:
    """Return True if Postgres answers `SELECT 1` within `timeout` seconds."""
    try:
        import psycopg

        async def _do() -> bool:
            async with await psycopg.AsyncConnection.connect(
                dsn, autocommit=True, connect_timeout=int(timeout),
                gssencmode="disable",
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    return True

        return bool(await asyncio.wait_for(_do(), timeout=timeout))
    except Exception:
        return False


async def _drop_legacy_checkpoint_tables(dsn: str) -> None:
    """Drop checkpoint* tables when their schema is stale.

    Runs once per process, before the saver opens its pool. Any failure is
    swallowed — we'd rather let saver.setup() try (and maybe succeed) than
    fail app startup on a migration check.
    """
    try:
        import psycopg

        async def _probe() -> None:
            async with await psycopg.AsyncConnection.connect(
                dsn, autocommit=True, connect_timeout=10,
                gssencmode="disable",
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_name = 'checkpoints'
                          AND column_name = 'checkpoint'
                        """
                    )
                    row = await cur.fetchone()
                    if row and row[0] == "bytea":
                        for table in (
                            "checkpoint_writes",
                            "checkpoint_blobs",
                            "checkpoint_migrations",
                            "checkpoints",
                        ):
                            await cur.execute(
                                f"DROP TABLE IF EXISTS {table} CASCADE"  # noqa: S608
                            )
                        from loguru import logger
                        logger.warning(
                            "Dropped legacy langgraph checkpoint tables (bytea schema); "
                            "saver.setup() will recreate them as jsonb."
                        )

        await asyncio.wait_for(_probe(), timeout=15)
    except Exception as exc:
        from loguru import logger
        logger.debug("Legacy checkpoint schema probe skipped: {}", exc)


async def close_checkpointer() -> None:
    """Close the cached saver's connection pool — call from app shutdown."""
    global _saver, _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
    _saver = None
    _pool = None


async def build_supervisor_graph(llm=None):
    settings = get_settings()
    if llm is None:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.agent_model,
            openai_api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            openai_proxy=settings.http_proxy or None,
        )

    vector_store = get_vector_store()
    redis = None
    try:
        from mediaforge.db.redis_client import get_redis
        redis = await get_redis()
    except Exception:
        pass
    rag_tool = RAGSearchTool(vector_store, redis=redis)

    agents = {
        ExpertAgent.IMAGE: create_agent(
            llm,
            tools=[rag_tool, StyleAnalyzerTool(), GenerateImageTool()],
            name=ExpertAgent.IMAGE,
            system_prompt=(
                "你是一名电商产品图片生成专家，遵循以下步骤：\n"
                "1. 如果用户提到了参考商品（如 SKU001）但没给图片 URL，先调用 rag_search 检索参考库获取参考图。\n"
                "2. 如果有参考图（来自检索或用户提供），调用 analyze_style 分析视觉风格，获取 style_prompt。\n"
                "3. 结合用户需求和 style_prompt（如有）构造完整的英文生图 prompt。\n"
                "4. 调用 generate_image 工具生成图片。\n"
                "   - 若用户提供了产品图片，通过 product_image_url 传入。\n"
                "   - 若有参考图，通过 ref_image_url 传入。\n"
                "   - aspect_ratio 默认 1:1（亚马逊主图），用户指定时以用户为准。\n"
                "没有参考图时直接根据文字描述调用 generate_image。"
            ),
        ),
        ExpertAgent.VIDEO: create_agent(
            llm,
            tools=[GenerateVideoTool()],
            name=ExpertAgent.VIDEO,
            system_prompt="你是一名短视频生成专家。根据用户需求调用 generate_video 工具生成产品展示短视频。",
        ),
        ExpertAgent.COMPLIANCE: create_agent(
            llm,
            tools=[CheckComplianceTool()],
            name=ExpertAgent.COMPLIANCE,
            system_prompt="你是跨境电商合规审查专家。调用 check_compliance 工具检查提示词是否符合目标市场的文化与平台规则。",
        ),
        ExpertAgent.RAG: create_agent(
            llm,
            tools=[rag_tool],
            name=ExpertAgent.RAG,
            system_prompt="你是产品参考库检索专家。调用 rag_search 在参考库中检索相似商品，并总结检索结果给用户。",
        ),
    }
    members = [e.value for e in ExpertAgent]

    class State(MessagesState):
        next: str

    async def supervisor_node(state: State) -> dict:
        router_llm = llm.with_structured_output(Router, method="json_schema")
        system_msg = (
            "你是 MediaForge 智能助手，也是一名调度员，负责把用户的请求路由给合适的专家处理。\n"
            f"可用专家: {members}。当请求已经被完整回答、无需任何专家介入时，返回 FINISH。\n"
            "选择下一步要执行的专家，或者返回 FINISH。\n\n"
            "你必须只返回一个 JSON 对象（不是数组），严格符合如下 schema:\n"
            '{"next": "<从 ' + ", ".join(members) + ' 或 FINISH 中选一个>"}\n'
            '示例: {"next": "image_agent"}'
        )
        # `callbacks=[]` keeps the router's JSON tokens out of the SSE stream.
        # The structured output is consumed internally for routing; only the
        # closing reply (generated below) should reach the user.
        try:
            decision = await router_llm.ainvoke(
                [SystemMessage(content=system_msg)] + state["messages"],
                config={"callbacks": []},
            )
        except Exception:
            # Fallback: ask plain LLM and parse manually
            import json, re
            from loguru import logger
            logger.warning("Structured output failed, falling back to plain JSON parse")
            plain = await llm.ainvoke(
                [SystemMessage(content=system_msg)] + state["messages"],
                config={"callbacks": []},
            )
            raw = plain.content if hasattr(plain, "content") else str(plain)
            # strip array wrapper if present: [{"next": "x"}] → {"next": "x"}
            raw = raw.strip()
            m = re.search(r'\{[^{}]*"next"\s*:\s*"([^"]+)"[^{}]*\}', raw)
            next_val = m.group(1) if m else "FINISH"
            if next_val not in members and next_val != "FINISH":
                next_val = "FINISH"
            decision = Router(next=next_val)

        # If the supervisor is about to finish and no assistant message has
        # been emitted yet (common for greetings / chit-chat that don't
        # route to any specialist), generate a short friendly closing so the
        # SSE stream isn't empty.
        if decision.next == "FINISH" and not any(
            getattr(m, "type", None) == "ai" for m in state["messages"]
        ):
            try:
                closing = await asyncio.wait_for(
                    llm.ainvoke(
                        [
                            SystemMessage(
                                content=(
                                    "你是 MediaForge 智能电商创意助手。请用用户的语言简短友好地回复。"
                                    "如果用户只是在打招呼，请回以问候，并简要介绍你能提供的能力："
                                    "生成产品图片、生成短视频、合规检查、产品参考库检索。"
                                    "控制在 1-2 句话以内。"
                                )
                            )
                        ]
                        + state["messages"]
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                closing = AIMessage(content="你好！我是 MediaForge 智能助手，可以帮您生成产品图片、短视频、合规检查和参考库检索。")
            return {"next": "FINISH", "messages": [closing]}

        return {"next": decision.next}

    def make_agent_node(name: str):
        agent = agents[ExpertAgent(name)]

        async def node(state: State) -> dict:
            from loguru import logger
            try:
                result = await asyncio.wait_for(
                    agent.ainvoke({"messages": state["messages"]}),
                    timeout=300,
                )
                return {"messages": result["messages"]}
            except asyncio.TimeoutError:
                logger.error("Agent {} timed out after 300s", name)
                return {"messages": [AIMessage(content=f"抱歉，{name} 执行超时，请稍后重试。")]}
            except Exception as exc:
                logger.exception("Agent {} failed: {}", name, exc)
                return {"messages": [AIMessage(content=f"抱歉，{name} 执行时遇到错误，请稍后重试。")]}

        return node

    workflow = StateGraph(State)
    workflow.add_node("supervisor", supervisor_node)
    for name in members:
        workflow.add_node(name, make_agent_node(name))

    workflow.add_edge(START, "supervisor")

    def route(state: State) -> str:
        nxt = state.get("next", "FINISH")
        if nxt == "FINISH" or nxt not in members:
            return END
        return nxt

    workflow.add_conditional_edges(
        "supervisor",
        route,
        {name: name for name in members} | {"FINISH": END, END: END},
    )
    for name in members:
        workflow.add_edge(name, "supervisor")

    saver = await _get_saver()
    return workflow.compile(checkpointer=saver)
