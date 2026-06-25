import asyncio
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, RemoveMessage, ToolMessage
from loguru import logger

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_tenant_only
from mediaforge.models.tenant import Tenant
from mediaforge.observability.cost_tracker import CostTracker
from mediaforge.orchestrator.agent_graph import build_supervisor_graph

router = APIRouter(prefix="/api/v1/agent")

_graph = None
_graph_lock = asyncio.Lock()


async def _get_graph():
    global _graph
    if _graph is not None:
        return _graph
    async with _graph_lock:
        if _graph is None:
            _graph = await build_supervisor_graph()
    return _graph


@router.delete("/history")
async def clear_history(
    session_id: str | None = None,
    tenant: Tenant = Depends(get_tenant_only),
):
    tenant_id_str = str(tenant.tenant_id)
    thread_id = session_id or tenant_id_str
    graph = await _get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await graph.aget_state(config)
        if state and state.values.get("messages"):
            removals = [RemoveMessage(id=m.id) for m in state.values["messages"] if getattr(m, "id", None)]
            if removals:
                await graph.aupdate_state(config, {"messages": removals})
    except Exception as exc:
        logger.warning("clear_history failed: {}", exc)
    return {"ok": True}


@router.get("/history")
async def get_history(
    session_id: str | None = None,
    tenant: Tenant = Depends(get_tenant_only),
):
    tenant_id_str = str(tenant.tenant_id)
    thread_id = session_id or tenant_id_str
    graph = await _get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await graph.aget_state(config)
    except Exception as exc:
        logger.warning("aget_state failed: {}", exc)
        return {"messages": []}
    messages = []
    if state and state.values.get("messages"):
        for msg in state.values["messages"]:
            msg_type = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
            if not content or not isinstance(content, str):
                continue
            if msg_type == "human":
                messages.append({"role": "user", "content": content})
            elif msg_type == "ai" and content.strip():
                messages.append({"role": "assistant", "content": content})
    return {"messages": messages}


@router.post("/chat")
async def chat(
    request: Request,
    payload: dict,
    tenant: Tenant = Depends(get_tenant_only),
):
    graph = await _get_graph()
    message = payload.get("message", "")
    tenant_id_str = str(tenant.tenant_id)
    thread_id = payload.get("session_id", tenant_id_str)
    trace_id = (
        request.state.trace_id
        if hasattr(request.state, "trace_id")
        else str(uuid.uuid4())
    )

    async def event_generator():
        total_tokens = 0
        assistant_content_parts: list[str] = []
        seen_ids: set = set()

        queue: asyncio.Queue = asyncio.Queue()

        async def _run_graph():
            try:
                async for msg, metadata in graph.astream(
                    {"messages": [HumanMessage(content=message)]},
                    {"configurable": {"thread_id": thread_id}, "recursion_limit": 25},
                    stream_mode="messages",
                ):
                    await queue.put(("msg", msg))
            except Exception as exc:
                await queue.put(("error", exc))
            finally:
                await queue.put(("done", None))

        graph_task = asyncio.create_task(_run_graph())

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                kind, data = item
                if kind == "done":
                    break
                if kind == "error":
                    logger.error("Graph error: {}", data)
                    break

                msg = data
                msg_id = getattr(msg, "id", None) or id(msg)
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                content = getattr(msg, "content", None)
                if not content or not isinstance(content, str) or not content.strip():
                    continue
                msg_type = getattr(msg, "type", "")

                if msg_type == "ai" or isinstance(msg, (AIMessage, AIMessageChunk)):
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls and not content.strip():
                        continue
                    yield f"data: {content}\n\n"
                    assistant_content_parts.append(content)
                    usage = getattr(msg, "usage_metadata", None)
                    if usage:
                        total_tokens += usage.get("total_tokens", 0) if isinstance(usage, dict) else getattr(usage, "total_tokens", 0)

                elif msg_type == "tool" or isinstance(msg, ToolMessage):
                    logger.debug("ToolMessage (not streamed): {}", content[:120])
        finally:
            graph_task.cancel()
            try:
                await graph_task
            except asyncio.CancelledError:
                pass

        tracker = CostTracker()
        await tracker.record(
            tenant_id_str,
            thread_id,
            [{"model": get_settings().agent_model, "count": 1, "tokens": total_tokens}],
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Trace-Id": trace_id},
    )
