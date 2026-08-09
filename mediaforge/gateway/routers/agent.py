import asyncio
import json
import re
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_current_principal
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.tenant import Tenant
from mediaforge.models.user import User
from mediaforge.observability.cost_tracker import CostTracker
from mediaforge.orchestrator.agent_graph import build_supervisor_graph

router = APIRouter(prefix="/api/v1/agent")

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
BUSINESS_TOOL_NAMES = {
    "rag_search",
    "check_image_compliance",
    "submit_generation_job",
    "get_generation_job",
}

_graphs: OrderedDict[str, object] = OrderedDict()
_graph_lock = asyncio.Lock()


class AgentChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    product_sku: str | None = Field(default=None, min_length=1, max_length=64)
    uploaded_image_url: str | None = Field(default=None, max_length=2048)
    uploaded_image_name: str | None = Field(default=None, max_length=255)
    target_platform: str | None = Field(default=None, max_length=32)

    @field_validator("target_platform")
    @classmethod
    def _validate_target_platform(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        platform = value.strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        return platform


class AgentConfirmPayload(BaseModel):
    confirmation_id: uuid.UUID
    target_platforms: list[str] | None = None
    output_types: list[str] | None = None
    presentation_mode: Literal["auto", "model_wear", "product_only"] | None = None
    model_preference: Literal["auto", "female", "male", "no_face"] | None = None
    style_hint: str | None = Field(default=None, max_length=500)
    image_model: Literal["pro", "fast", "base"] | None = None
    aspect_ratio: Literal["auto", "1:1", "3:4", "4:5", "9:16", "16:9", "4:1", "1:4"] | None = None
    image_size: Literal["1K", "2K", "4K"] | None = None
    reference_mode: Literal["specified", "none"] | None = None

    @field_validator("target_platforms")
    @classmethod
    def _validate_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        platforms = list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if not platforms:
            raise ValueError("至少选择一个目标平台")
        unsupported = sorted(set(platforms) - SUPPORTED_PLATFORMS)
        if unsupported:
            raise ValueError(f"不支持的平台: {', '.join(unsupported)}")
        return platforms

    @field_validator("output_types")
    @classmethod
    def _validate_output_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"main_image", "detail_page", "pdd_white_background"}
        outputs = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not outputs:
            raise ValueError("至少选择一种输出类型")
        unsupported = sorted(set(outputs) - allowed)
        if unsupported:
            raise ValueError(f"不支持的输出类型: {', '.join(unsupported)}")
        return outputs

    @model_validator(mode="after")
    def _validate_platform_outputs(self):
        if (
            self.output_types
            and "pdd_white_background" in self.output_types
            and self.target_platforms
            and "pinduoduo" not in self.target_platforms
        ):
            raise ValueError("拼多多白底图只能用于拼多多平台")
        return self


class AgentFeedbackPayload(BaseModel):
    trace_id: uuid.UUID
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    rating: Literal["helpful", "unhelpful"]


class AgentConfigurationResponse(BaseModel):
    prompt_version: str
    prompt_hash: str
    toolset_version: str
    model: str
    temperature: float
    rag_min_score: float


class AgentSessionCreatePayload(BaseModel):
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    title: str = Field(default="新对话", min_length=1, max_length=100)


class AgentSessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class AgentSessionListResponse(BaseModel):
    sessions: list[AgentSessionResponse]


def _principal_thread_id(tenant_id: str, user_id: str, session_id: str | None) -> str:
    return f"{tenant_id}:{user_id}:{session_id or 'default'}"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _trusted_message(payload: AgentChatPayload, tenant: Tenant, user: User) -> str:
    selected_product: dict | None = None
    uploaded_product: dict | None = None
    if payload.product_sku:
        from sqlalchemy import case, or_, select

        from mediaforge.db.engine import get_engine
        from mediaforge.db.tables import ProductTable

        table = ProductTable.__table__
        visible = or_(
            table.c.visibility == "global",
            table.c.tenant_id == tenant.tenant_id,
        )
        async with get_engine().connect() as connection:
            row = (
                await connection.execute(
                    select(
                        table.c.sku_code,
                        table.c.image_url,
                        table.c.category,
                        table.c.style,
                        table.c.color,
                        table.c.material,
                        table.c.description,
                    )
                    .where(visible, table.c.sku_code == payload.product_sku)
                    .order_by(case((table.c.tenant_id == tenant.tenant_id, 0), else_=1))
                    .limit(1)
                )
            ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="商品不存在或当前企业无权访问")
        selected_product = dict(row)
    if payload.uploaded_image_url:
        settings = get_settings()
        expected_prefix = (
            f"{settings.minio_public_base_url.rstrip('/')}/uploads/{tenant.tenant_id}/"
        )
        if not payload.uploaded_image_url.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="上传图片地址无效")
        uploaded_product = {
            "image_url": payload.uploaded_image_url,
            "image_name": payload.uploaded_image_name or "上传商品图",
            "source": "tenant_upload",
        }

    from sqlalchemy import select, update

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    session_table = AgentSessionTable.__table__
    async with get_engine().begin() as connection:
        saved_context = (
            await connection.execute(
                select(session_table.c.context).where(
                    session_table.c.user_id == user.user_id,
                    session_table.c.tenant_id == tenant.tenant_id,
                    session_table.c.session_id == payload.session_id,
                )
            )
        ).scalar_one_or_none() or {}
        business_data = dict(saved_context)
        if selected_product:
            business_data["selected_product"] = selected_product
            business_data["active_source"] = "selected_product"
        if uploaded_product:
            business_data["uploaded_product"] = uploaded_product
            business_data["active_source"] = "uploaded_product"
        if payload.target_platform:
            business_data["target_platform"] = payload.target_platform
        if selected_product or uploaded_product or payload.target_platform:
            await connection.execute(
                update(session_table)
                .where(
                    session_table.c.user_id == user.user_id,
                    session_table.c.tenant_id == tenant.tenant_id,
                    session_table.c.session_id == payload.session_id,
                )
                .values(context=business_data)
            )

    if not business_data:
        return payload.message.strip()
    return (
        f"{payload.message.strip()}\n\n"
        "<business_data source=\"trusted_backend\">\n"
        f"{json.dumps(business_data, ensure_ascii=False)}\n"
        "</business_data>"
    )


async def _remember_retrieved_reference(
    *,
    result: dict,
    tenant: Tenant,
    user: User,
    session_id: str,
) -> None:
    """Carry the top visual-search result into the next generation turn."""
    candidates = result.get("results") or []
    if not result.get("matched") or not candidates:
        return
    candidate = candidates[0]
    product_id = str(candidate.get("product_id") or "").strip()
    image_url = str(candidate.get("image_url") or "").strip()
    if not product_id or not image_url:
        return

    from sqlalchemy import select, update

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    table = AgentSessionTable.__table__
    async with get_engine().begin() as connection:
        context = (
            await connection.execute(
                select(table.c.context).where(
                    table.c.user_id == user.user_id,
                    table.c.tenant_id == tenant.tenant_id,
                    table.c.session_id == session_id,
                )
            )
        ).scalar_one_or_none() or {}
        # A retrieved bestseller is a style reference only when the active
        # product is an uploaded image. Do not replace a library product source.
        if context.get("active_source") != "uploaded_product":
            return
        context["selected_product"] = {
            "sku_code": product_id,
            "image_url": image_url,
            "category": candidate.get("category") or "",
            "style": candidate.get("style") or "",
            "color": candidate.get("color") or "",
            "material": candidate.get("material") or "",
            "description": "",
        }
        context["active_source"] = "uploaded_product"
        await connection.execute(
            update(table)
            .where(
                table.c.user_id == user.user_id,
                table.c.tenant_id == tenant.tenant_id,
                table.c.session_id == session_id,
            )
            .values(context=context)
        )


def _business_context_from_content(content: str) -> dict:
    marker = "\n\n<business_data"
    if marker not in content:
        return {}

    try:
        block = content.split(marker, 1)[1]
        payload_text = block.split(">\n", 1)[1].split("\n</business_data>", 1)[0]
        business_data = json.loads(payload_text)
    except (IndexError, TypeError, json.JSONDecodeError):
        logger.warning("Unable to parse persisted agent business context")
        return {}

    if "selected_product" in business_data or "uploaded_product" in business_data:
        return business_data
    if business_data.get("source") == "tenant_upload":
        return {"uploaded_product": business_data, "active_source": "uploaded_product"}
    if business_data.get("sku_code"):
        return {"selected_product": business_data, "active_source": "selected_product"}
    return {}


def _human_message_response(content: str) -> dict:
    visible_content = content.split("\n\n[商品上下文]", 1)[0]
    marker = "\n\n<business_data"
    if marker not in content:
        return {"role": "user", "content": visible_content}

    visible_content = content.split(marker, 1)[0]
    response = {"role": "user", "content": visible_content}
    business_data = _business_context_from_content(content)
    try:
        context_images = []
        uploaded = business_data.get("uploaded_product") or {}
        if uploaded.get("image_url"):
            context_images.append(
                {
                    "url": uploaded["image_url"],
                    "label": uploaded.get("image_name", "上传商品图"),
                    "source": "upload",
                }
            )
        selected = business_data.get("selected_product") or {}
        if selected.get("image_url"):
            context_images.append(
                {
                    "url": selected["image_url"],
                    "label": " · ".join(
                        value
                        for value in (selected.get("sku_code"), selected.get("category"))
                        if value
                    ),
                    "source": "product",
                }
            )
        if context_images:
            response["contextImages"] = context_images
            first = context_images[0]
            response.update(
                {
                    "contextImageUrl": first["url"],
                    "contextLabel": first["label"],
                    "contextSource": first["source"],
                }
            )
    except (AttributeError, TypeError):
        logger.warning("Unable to render persisted agent business context")
    return response


async def _get_graph(
    tenant_id: str,
    user_id: str,
    session_id: str,
    graph_scope: str = "state",
    allowed_tool_names: frozenset[str] = frozenset(),
):
    key = f"{tenant_id}:{user_id}:{session_id}:{graph_scope}"
    if key in _graphs:
        graph = _graphs.pop(key)
        _graphs[key] = graph
        return graph
    async with _graph_lock:
        if key not in _graphs:
            _graphs[key] = await build_supervisor_graph(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                allowed_tool_names=allowed_tool_names,
            )
            while len(_graphs) > get_settings().agent_graph_cache_size:
                _graphs.popitem(last=False)
    return _graphs[key]


async def _acquire_tenant_slot(tenant_id: str) -> bool:
    from mediaforge.db.redis_client import get_redis

    redis = await get_redis()
    key = f"agent:concurrency:{tenant_id}"
    script = """
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    if current >= tonumber(ARGV[1]) then return 0 end
    current = redis.call('INCR', KEYS[1])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return current
    """
    result = await redis.eval(
        script,
        1,
        key,
        get_settings().agent_concurrency_per_tenant,
        180,
    )
    return bool(result)


async def _release_tenant_slot(tenant_id: str) -> None:
    from mediaforge.db.redis_client import get_redis

    redis = await get_redis()
    key = f"agent:concurrency:{tenant_id}"
    await redis.eval(
        "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); "
        "if n<=1 then redis.call('DEL',KEYS[1]); return 0; "
        "else return redis.call('DECR',KEYS[1]); end",
        1,
        key,
    )


async def _touch_agent_session(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: str,
    message: str,
) -> None:
    from sqlalchemy import select, update

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    table = AgentSessionTable.__table__
    now = datetime.now(timezone.utc)
    candidate_title = message.strip().splitlines()[0][:18] or "新对话"
    async with get_engine().begin() as connection:
        row = (
            await connection.execute(
                select(table.c.title).where(
                    table.c.user_id == user_id,
                    table.c.session_id == session_id,
                    table.c.tenant_id == tenant_id,
                )
            )
        ).first()
        if row is None:
            await connection.execute(
                table.insert().values(
                    user_id=user_id,
                    session_id=session_id,
                    tenant_id=tenant_id,
                    title=candidate_title,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            values: dict = {"updated_at": now}
            if row.title in {"新对话", "默认对话"}:
                values["title"] = candidate_title
            await connection.execute(
                update(table)
                .where(table.c.user_id == user_id, table.c.session_id == session_id)
                .values(**values)
            )


async def _clear_thread_messages(tenant: Tenant, user: User, session_id: str) -> None:
    tenant_id_str = str(tenant.tenant_id)
    thread_id = _principal_thread_id(tenant_id_str, str(user.user_id), session_id)
    graph = await _get_graph(tenant_id_str, str(user.user_id), session_id)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await graph.aget_state(config)
        if state and state.values.get("messages"):
            removals = [
                RemoveMessage(id=message.id)
                for message in state.values["messages"]
                if getattr(message, "id", None)
            ]
            if removals:
                await graph.aupdate_state(config, {"messages": removals})
    except Exception as exc:
        logger.warning("clear_history failed: {}", exc)


@router.get("/configuration", response_model=AgentConfigurationResponse)
async def agent_configuration(
    principal: tuple[User, Tenant] = Depends(get_current_principal),
) -> AgentConfigurationResponse:
    del principal
    settings = get_settings()
    from mediaforge.orchestrator.agent_prompt import get_prompt
    from mediaforge.orchestrator.agent_tools import AGENT_TOOLSET_VERSION

    prompt_version, prompt_hash, _ = get_prompt(settings.agent_prompt_version)
    return AgentConfigurationResponse(
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        toolset_version=AGENT_TOOLSET_VERSION,
        model=settings.agent_model,
        temperature=settings.agent_temperature,
        rag_min_score=settings.agent_rag_min_score,
    )


@router.get("/sessions", response_model=AgentSessionListResponse)
async def list_agent_sessions(
    principal: tuple[User, Tenant] = Depends(get_current_principal),
) -> AgentSessionListResponse:
    from sqlalchemy import select

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    user, tenant = principal
    table = AgentSessionTable.__table__
    async with get_engine().connect() as connection:
        rows = (
            await connection.execute(
                select(
                    table.c.session_id,
                    table.c.title,
                    table.c.created_at,
                    table.c.updated_at,
                )
                .where(
                    table.c.user_id == user.user_id,
                    table.c.tenant_id == tenant.tenant_id,
                )
                .order_by(table.c.updated_at.desc())
            )
        ).mappings().all()
    return AgentSessionListResponse(
        sessions=[AgentSessionResponse(**dict(row)) for row in rows]
    )


@router.post("/sessions", response_model=AgentSessionResponse)
async def create_agent_session(
    payload: AgentSessionCreatePayload,
    principal: tuple[User, Tenant] = Depends(get_current_principal),
) -> AgentSessionResponse:
    from sqlalchemy.dialects.postgresql import insert

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    user, tenant = principal
    table = AgentSessionTable.__table__
    session_id = payload.session_id or str(uuid.uuid4())
    title = payload.title.strip() or "新对话"
    now = datetime.now(timezone.utc)
    statement = insert(table).values(
        user_id=user.user_id,
        session_id=session_id,
        tenant_id=tenant.tenant_id,
        title=title,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[table.c.user_id, table.c.session_id],
        set_={"title": title, "updated_at": now},
    ).returning(
        table.c.session_id,
        table.c.title,
        table.c.created_at,
        table.c.updated_at,
    )
    async with get_engine().begin() as connection:
        row = (await connection.execute(statement)).mappings().one()
    return AgentSessionResponse(**dict(row))


@router.delete("/sessions/{session_id}")
async def delete_agent_session(
    session_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    from sqlalchemy import delete, select

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable

    user, tenant = principal
    table = AgentSessionTable.__table__
    async with get_engine().connect() as connection:
        exists = (
            await connection.execute(
                select(table.c.session_id).where(
                    table.c.user_id == user.user_id,
                    table.c.tenant_id == tenant.tenant_id,
                    table.c.session_id == session_id,
                )
            )
        ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    tenant_id_str = str(tenant.tenant_id)
    graph_prefix = f"{tenant_id_str}:{user.user_id}:{session_id}"
    matching_keys = [key for key in _graphs if key == graph_prefix or key.startswith(f"{graph_prefix}:")]
    graph = None
    for key in matching_keys:
        graph = _graphs.pop(key)
    if graph is None:
        graph = await build_supervisor_graph(
            tenant_id=tenant_id_str,
            user_id=str(user.user_id),
            session_id=session_id,
            allowed_tool_names=frozenset(),
        )
    checkpointer = getattr(graph, "checkpointer", None)
    if checkpointer is not None and hasattr(checkpointer, "adelete_thread"):
        await checkpointer.adelete_thread(
            _principal_thread_id(tenant_id_str, str(user.user_id), session_id)
        )

    async with get_engine().begin() as connection:
        await connection.execute(
            delete(table).where(
                table.c.user_id == user.user_id,
                table.c.tenant_id == tenant.tenant_id,
                table.c.session_id == session_id,
            )
        )
    return {"ok": True}


@router.delete("/history")
async def clear_history(
    session_id: Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")] = "default",
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    user, tenant = principal
    await _clear_thread_messages(tenant, user, session_id)
    return {"ok": True}


@router.get("/history")
async def get_history(
    session_id: Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")] = "default",
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    user, tenant = principal
    tenant_id_str = str(tenant.tenant_id)
    thread_id = _principal_thread_id(tenant_id_str, str(user.user_id), session_id)
    graph = await _get_graph(tenant_id_str, str(user.user_id), session_id)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await graph.aget_state(config)
    except Exception as exc:
        logger.warning("aget_state failed: {}", exc)
        return {"messages": []}
    from sqlalchemy import select

    from mediaforge.db.engine import get_engine
    from mediaforge.db.tables import AgentSessionTable, JobTable

    session_table = AgentSessionTable.__table__
    job_table = JobTable.__table__
    async with get_engine().connect() as connection:
        session_context = (
            await connection.execute(
                select(session_table.c.context).where(
                    session_table.c.user_id == user.user_id,
                    session_table.c.tenant_id == tenant.tenant_id,
                    session_table.c.session_id == session_id,
                )
            )
        ).scalar_one_or_none() or {}

        confirmed_jobs = {
            str(key): str(value)
            for key, value in (session_context.get("confirmed_jobs") or {}).items()
        }
        confirmation_ids: set[str] = set()
        if state and state.values.get("messages"):
            for state_message in state.values["messages"]:
                if getattr(state_message, "type", "") != "tool":
                    continue
                if getattr(state_message, "name", "") != "submit_generation_job":
                    continue
                try:
                    state_result = json.loads(getattr(state_message, "content", ""))
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(state_result, dict) and state_result.get("confirmation_id"):
                    confirmation_ids.add(str(state_result["confirmation_id"]))

        missing_confirmation_ids = confirmation_ids - confirmed_jobs.keys()
        if missing_confirmation_ids:
            rows = (
                await connection.execute(
                    select(job_table.c.idempotency_key, job_table.c.job_id).where(
                        job_table.c.tenant_id == tenant.tenant_id,
                        job_table.c.created_by == user.user_id,
                        job_table.c.source == "agent",
                        job_table.c.idempotency_key.in_(missing_confirmation_ids),
                    )
                )
            ).all()
            confirmed_jobs.update({str(row.idempotency_key): str(row.job_id) for row in rows})

    messages = []
    pending_result: dict = {}
    restored_context: dict = {}
    if state and state.values.get("messages"):
        for msg in state.values["messages"]:
            msg_type = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
            if not content or not isinstance(content, str):
                continue
            if msg_type == "human":
                pending_result = {}
                item_context = _business_context_from_content(content)
                if item_context.get("uploaded_product"):
                    restored_context["uploaded_product"] = item_context["uploaded_product"]
                if item_context.get("selected_product"):
                    restored_context["selected_product"] = item_context["selected_product"]
                if item_context.get("active_source"):
                    restored_context["active_source"] = item_context["active_source"]
                messages.append(_human_message_response(content))
            elif msg_type == "tool":
                try:
                    tool_result = json.loads(content)
                except (TypeError, json.JSONDecodeError):
                    tool_result = None
                tool_name = getattr(msg, "name", "")
                if not isinstance(tool_result, dict):
                    continue
                if tool_name == "rag_search" and tool_result.get("ok") is not False:
                    pending_result["referenceResult"] = tool_result
                elif tool_name == "check_image_compliance":
                    pending_result["qualityResult"] = tool_result
                elif tool_name == "submit_generation_job" and tool_result.get("status") == "confirmation_required":
                    confirmation_id = str(tool_result.get("confirmation_id") or "")
                    confirmed_job_id = confirmed_jobs.get(confirmation_id)
                    if confirmed_job_id:
                        pending_result["taskId"] = confirmed_job_id
                        pending_result.pop("confirmation", None)
                    else:
                        pending_result["confirmation"] = tool_result
                elif tool_name == "get_generation_job" and tool_result.get("job_id"):
                    pending_result["taskId"] = str(tool_result["job_id"])
                if tool_result.get("ok") is False:
                    pending_result["toolFailure"] = {
                        "code": tool_result.get("error_code"),
                        "message": tool_result.get("message"),
                        "retryable": bool(tool_result.get("retryable")),
                    }
            elif msg_type == "ai" and content.strip():
                messages.append({"role": "assistant", "content": content, **pending_result})
                pending_result = {}
    if restored_context:
        from sqlalchemy import update
        session_context.update(restored_context)
        table = session_table
        async with get_engine().begin() as connection:
            await connection.execute(
                update(table)
                .where(
                    table.c.user_id == user.user_id,
                    table.c.tenant_id == tenant.tenant_id,
                    table.c.session_id == session_id,
                )
                .values(context=session_context)
            )
    return {"messages": messages, "context": session_context}


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    payload: AgentChatPayload,
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    user, tenant = principal
    tenant_id_str = str(tenant.tenant_id)
    from mediaforge.orchestrator.agent_intent import (
        classify_agent_intent,
        fallback_response,
        help_response,
        tools_for_intent,
    )

    route = classify_agent_intent(payload.message)
    direct_answer = None
    if route.intent == "help":
        direct_answer = help_response(payload.message)
    elif route.intent == "conversation_fallback":
        direct_answer = fallback_response()
    try:
        acquired = await _acquire_tenant_slot(tenant_id_str)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="助手并发控制服务暂时不可用") from exc
    if not acquired:
        raise HTTPException(status_code=429, detail="当前企业的助手请求较多，请稍后重试")
    try:
        graph = await _get_graph(
            tenant_id_str,
            str(user.user_id),
            payload.session_id,
            route.intent,
            tools_for_intent(route.intent),
        )
    except Exception:
        await _release_tenant_slot(tenant_id_str)
        raise
    await _touch_agent_session(
        tenant.tenant_id,
        user.user_id,
        payload.session_id,
        payload.message,
    )
    message = await _trusted_message(payload, tenant, user)
    if route.intent == "reference_search" and direct_answer is None:
        from mediaforge.orchestrator.rag_tool import is_actionable_search_query

        business_data = _business_context_from_content(message)
        uploaded = business_data.get("uploaded_product") or {}
        selected = business_data.get("selected_product") or {}
        context_image = uploaded.get("image_url") or selected.get("image_url")
        if not is_actionable_search_query(payload.message, context_image):
            direct_answer = (
                "请先上传新品图，或从商品库选择一个商品；也可以直接补充品类、版型、颜色、材质等检索条件。"
            )
    thread_id = _principal_thread_id(tenant_id_str, str(user.user_id), payload.session_id)
    trace_id = (
        request.state.trace_id
        if hasattr(request.state, "trace_id")
        else str(uuid.uuid4())
    )
    settings = get_settings()
    from mediaforge.orchestrator.agent_prompt import get_prompt
    from mediaforge.orchestrator.agent_tools import AGENT_TOOLSET_VERSION

    prompt_version, prompt_hash, _ = get_prompt(settings.agent_prompt_version)

    async def event_generator():
        prompt_tokens = 0
        completion_tokens = 0
        started_tools: set[str] = set()
        verified_ids: set[str] = set()
        response_status = "unknown"

        queue: asyncio.Queue = asyncio.Queue()

        async def _run_graph():
            try:
                if direct_answer:
                    await graph.aupdate_state(
                        {"configurable": {"thread_id": thread_id}},
                        {"messages": [HumanMessage(content=message), AIMessage(content=direct_answer)]},
                    )
                    await queue.put(
                        (
                            "response",
                            {
                                "intent": route.intent,
                                "status": "answered",
                                "answer": direct_answer,
                                "evidence": [],
                            },
                        )
                    )
                    return
                async for msg, metadata in graph.astream(
                    {"messages": [HumanMessage(content=message)]},
                    {
                        "configurable": {"thread_id": thread_id},
                        "recursion_limit": settings.agent_recursion_limit,
                        "metadata": {
                            "tenant_id": tenant_id_str,
                            "user_id": str(user.user_id),
                            "session_id": payload.session_id,
                            "trace_id": trace_id,
                            "prompt_version": prompt_version,
                            "prompt_hash": prompt_hash,
                            "toolset_version": AGENT_TOOLSET_VERSION,
                            "agent_model": settings.agent_model,
                            "agent_temperature": settings.agent_temperature,
                            "intent": route.intent,
                        },
                    },
                    stream_mode="messages",
                ):
                    await queue.put(("msg", (msg, metadata)))
                state = await graph.aget_state(
                    {"configurable": {"thread_id": thread_id}}
                )
                structured = state.values.get("structured_response") if state else None
                if structured is not None:
                    payload_data = (
                        structured.model_dump()
                        if hasattr(structured, "model_dump")
                        else dict(structured)
                    )
                    answer = str(payload_data.get("answer") or "").strip()
                    messages = state.values.get("messages") or []
                    last_message = messages[-1] if messages else None
                    if answer and not (
                        isinstance(last_message, AIMessage)
                        and getattr(last_message, "content", "") == answer
                    ):
                        await graph.aupdate_state(
                            {"configurable": {"thread_id": thread_id}},
                            {"messages": [AIMessage(content=answer)]},
                        )
                    await queue.put(("response", payload_data))
            except Exception as exc:
                await queue.put(("error", exc))
            finally:
                await queue.put(("done", None))

        graph_task = asyncio.create_task(_run_graph())

        try:
            yield _sse({"type": "meta", "trace_id": trace_id, "intent": route.intent})
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
                    yield _sse(
                        {
                            "type": "error",
                            "message": "智能助手执行失败，请稍后重试。",
                            "trace_id": trace_id,
                        }
                    )
                    break
                if kind == "response":
                    response_status = str(data.get("status") or "unknown")
                    answer = str(data.get("answer") or "").strip()
                    unsupported_ids = {
                        value.lower() for value in UUID_PATTERN.findall(answer)
                    } - verified_ids
                    if unsupported_ids:
                        data = {
                            "status": "tool_error",
                            "answer": "业务工具没有返回可验证的任务标识，当前无法确认该任务信息。",
                        }
                        response_status = "tool_error"
                    data["evidence"] = sorted(started_tools)
                    yield _sse({"type": "response", "response": data})
                    continue

                msg, message_metadata = data
                content = getattr(msg, "content", None)
                msg_type = getattr(msg, "type", "")

                if msg_type == "ai" or isinstance(msg, (AIMessage, AIMessageChunk)):
                    if message_metadata.get("langgraph_node") == "tools":
                        continue
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    tool_chunks = getattr(msg, "tool_call_chunks", None) or []
                    for call in [*tool_calls, *tool_chunks]:
                        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                        if name in BUSINESS_TOOL_NAMES and name not in started_tools:
                            started_tools.add(name)
                            yield _sse({"type": "tool", "name": name, "status": "running"})
                    if content and isinstance(content, str) and content.strip():
                        yield _sse({"type": "content", "content": content})
                    usage = getattr(msg, "usage_metadata", None)
                    if usage:
                        if isinstance(usage, dict):
                            prompt_tokens = max(prompt_tokens, int(usage.get("input_tokens", 0)))
                            completion_tokens = max(completion_tokens, int(usage.get("output_tokens", 0)))
                        else:
                            prompt_tokens = max(prompt_tokens, int(getattr(usage, "input_tokens", 0)))
                            completion_tokens = max(completion_tokens, int(getattr(usage, "output_tokens", 0)))

                elif msg_type == "tool" or isinstance(msg, ToolMessage):
                    name = getattr(msg, "name", None) or "tool"
                    if name in BUSINESS_TOOL_NAMES:
                        yield _sse({"type": "tool", "name": name, "status": "done"})
                    if isinstance(content, str):
                        logger.debug("ToolMessage: {}", content[:120])
                        try:
                            result = json.loads(content)
                        except (TypeError, json.JSONDecodeError):
                            result = None
                        if not isinstance(result, dict):
                            continue
                        if name == "rag_search" and result.get("ok") is not False:
                            await _remember_retrieved_reference(
                                result=result,
                                tenant=tenant,
                                user=user,
                                session_id=payload.session_id,
                            )
                            yield _sse({"type": "reference_result", "result": result})
                        elif name == "check_image_compliance":
                            yield _sse({"type": "quality_result", "result": result})
                        if result.get("ok") is False:
                            yield _sse(
                                {
                                    "type": "tool_failure",
                                    "failure": {
                                        "code": result.get("error_code"),
                                        "message": result.get("message"),
                                        "retryable": bool(result.get("retryable")),
                                    },
                                }
                            )
                        if result.get("job_id"):
                            verified_ids.add(str(result["job_id"]).lower())
                            yield _sse({"type": "task", "job": result})
                        elif (
                            result.get("status") == "confirmation_required"
                        ):
                            if result.get("confirmation_id"):
                                verified_ids.add(str(result["confirmation_id"]).lower())
                            yield _sse({"type": "confirmation", "confirmation": result})
        finally:
            graph_task.cancel()
            try:
                await graph_task
            except asyncio.CancelledError:
                pass

        try:
            tracker = CostTracker()
            await tracker.record(
                tenant_id_str,
                thread_id,
                [{
                    "model": settings.agent_model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }],
            )
            from mediaforge.db.audit_store import audit
            await audit(
                "agent_chat",
                tenant_id=tenant_id_str,
                user_id=user.user_id,
                metadata={
                    "trace_id": trace_id,
                    "session_id": payload.session_id,
                    "prompt_version": prompt_version,
                    "prompt_hash": prompt_hash,
                    "toolset_version": AGENT_TOOLSET_VERSION,
                    "agent_model": settings.agent_model,
                    "agent_temperature": settings.agent_temperature,
                    "tools": sorted(started_tools),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "response_status": response_status,
                    "intent": route.intent,
                },
            )
        except Exception:
            logger.warning("Failed to persist assistant usage for {}", trace_id)
        finally:
            try:
                await _release_tenant_slot(tenant_id_str)
            except Exception:
                logger.warning("Failed to release distributed agent slot for {}", tenant_id_str)
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Trace-Id": trace_id},
    )


@router.post("/feedback")
async def record_agent_feedback(
    payload: AgentFeedbackPayload,
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    user, tenant = principal
    from mediaforge.db.audit_store import audit

    await audit(
        "agent_response_feedback",
        tenant_id=str(tenant.tenant_id),
        user_id=user.user_id,
        metadata={
            "trace_id": str(payload.trace_id),
            "session_id": payload.session_id,
            "rating": payload.rating,
        },
    )
    return {"ok": True}


@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_generation(
    request: Request,
    payload: AgentConfirmPayload,
    principal: tuple[User, Tenant] = Depends(get_current_principal),
):
    """Consume a pending confirmation and create one idempotent paid job."""
    from mediaforge.db.audit_store import audit
    from mediaforge.db.engine import get_engine
    from mediaforge.db.job_store import JobStore
    from mediaforge.db.redis_client import get_redis
    from mediaforge.models.job import BatchSubmitPayload
    from mediaforge.orchestrator.dispatcher import dispatch_generation_job

    user, tenant = principal
    tenant_id = str(tenant.tenant_id)
    user_id = str(user.user_id)
    confirmation_id = str(payload.confirmation_id)
    redis = await get_redis()
    store = JobStore(get_engine(), redis)
    key = f"agent:confirmation:{tenant_id}:{user_id}:{confirmation_id}"
    raw = await redis.execute_command("GETDEL", key)
    if raw is None:
        existing = await store.get_job_by_idempotency(tenant_id, confirmation_id)
        if existing:
            job_id = str(existing["job_id"])
            return JSONResponse(
                status_code=200,
                content={"job_id": job_id, "status": str(existing["status"]), "duplicate": True},
            )
        raise HTTPException(status_code=404, detail="确认信息已失效，请重新准备任务")

    pending = json.loads(raw)
    if pending.get("tenant_id") != tenant_id or pending.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="确认信息不存在")
    pending_payload = pending["payload"]
    if not pending_payload.get("skus"):
        raise HTTPException(status_code=400, detail="确认信息缺少商品配置")
    sku_payload = pending_payload["skus"][0]
    if payload.target_platforms is not None:
        from mediaforge.workers.platform_rules import infer_market

        sku_payload["target_platforms"] = payload.target_platforms
        sku_payload["market"] = infer_market(payload.target_platforms).upper()
    if payload.output_types is not None:
        sku_payload["output_types"] = payload.output_types
    if payload.presentation_mode is not None:
        sku_payload["presentation_mode"] = payload.presentation_mode
    if payload.model_preference is not None:
        sku_payload["model_preference"] = payload.model_preference
    if payload.style_hint is not None:
        sku_payload["style_hint"] = payload.style_hint.strip() or None
    if payload.aspect_ratio is not None:
        sku_payload["aspect_ratio"] = payload.aspect_ratio
    if payload.image_size is not None:
        sku_payload["image_size"] = payload.image_size
    if payload.image_model is not None:
        pending_payload["image_model"] = payload.image_model
    if payload.reference_mode == "none":
        sku_payload["reference_mode"] = "none"
        sku_payload["ref_sku_id"] = None
    elif payload.reference_mode == "specified" and sku_payload.get("ref_sku_id"):
        sku_payload["reference_mode"] = "specified"
    if (
        "pdd_white_background" in sku_payload.get("output_types", [])
        and "pinduoduo" not in sku_payload.get("target_platforms", [])
    ):
        raise HTTPException(status_code=422, detail="拼多多白底图只能用于拼多多平台")
    batch_payload = BatchSubmitPayload.model_validate(pending_payload)
    job_id = await dispatch_generation_job(
        tenant,
        batch_payload,
        store,
        idempotency_key=confirmation_id,
        created_by=user_id,
        source="agent",
    )
    from sqlalchemy import select, update

    from mediaforge.db.tables import AgentSessionTable

    session_id = str(pending.get("session_id") or "")
    if session_id:
        session_table = AgentSessionTable.__table__
        async with get_engine().begin() as connection:
            context = (
                await connection.execute(
                    select(session_table.c.context).where(
                        session_table.c.user_id == user.user_id,
                        session_table.c.tenant_id == tenant.tenant_id,
                        session_table.c.session_id == session_id,
                    )
                )
            ).scalar_one_or_none() or {}
            confirmed_jobs = dict(context.get("confirmed_jobs") or {})
            confirmed_jobs[confirmation_id] = str(job_id)
            context["confirmed_jobs"] = dict(list(confirmed_jobs.items())[-50:])
            await connection.execute(
                update(session_table)
                .where(
                    session_table.c.user_id == user.user_id,
                    session_table.c.tenant_id == tenant.tenant_id,
                    session_table.c.session_id == session_id,
                )
                .values(context=context)
            )
    await audit(
        "agent_job_confirmed",
        tenant_id=tenant_id,
        user_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "confirmation_id": confirmation_id,
            "job_id": job_id,
            "target_platforms": batch_payload.skus[0].target_platforms,
            "output_types": batch_payload.skus[0].output_types,
            **(pending.get("agent_release") or {}),
        },
    )
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "running", "task_url": f"/tasks?jobId={job_id}"},
    )
