import json

from langchain_core.runnables import RunnableConfig

from mediaforge.config import get_settings
from mediaforge.models.job import GenerationContext, SkuInput
from mediaforge.orchestrator.state import JobState
from mediaforge.rag.factory import get_vector_store
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image import (
    DetailPageWorker,
    MainImageWorker,
    PinduoduoWhiteBackgroundWorker,
    SocialWorker,
)
from mediaforge.workers.openrouter_client import OpenRouterClient
from mediaforge.workers.video import VeoWorker


def validate_job(state: JobState) -> dict:
    if not state["skus"]:
        raise ValueError("No SKUs in batch")
    return {"total_sku_count": len(state["skus"])}


def _sku_from_state(state: dict) -> SkuInput:
    raw_sku = state["skus"][0]
    return SkuInput.model_validate(raw_sku) if isinstance(raw_sku, dict) else raw_sku


def _effective_image_model(state: dict) -> str:
    return state.get("active_image_model") or state["image_model"]


async def prepare_generation_context(
    state: JobState, config: RunnableConfig | None = None
) -> dict:
    sku = _sku_from_state(state)
    settings = get_settings()
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    try:
        vector_store = get_vector_store()
    except Exception:
        vector_store = None
    preparer = MainImageWorker(
        client,
        model=_effective_image_model(state),
        vector_store=vector_store,
    )
    context = await preparer.prepare_generation_context(sku, state["tenant_id"])
    return {
        "generation_context": context.model_dump(mode="json"),
        "logs": [
            f"generation_context prepared {sku.sku_id}: "
            f"routes={','.join(context.retrieval_routes) or 'none'} "
            f"refs={len(context.reference_candidates)}"
        ],
    }


async def image_worker(state: dict, config: RunnableConfig | None = None) -> dict:
    sku = _sku_from_state(state)
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    result = WorkerResult()
    generation_context = GenerationContext.model_validate(state["generation_context"])
    if sku.presentation_mode == "auto":
        sku.presentation_mode = generation_context.presentation_mode
    effective_model = _effective_image_model(state)

    try:
        vector_store = get_vector_store()
    except Exception:
        vector_store = None

    worker_classes = [
        ("main_image", MainImageWorker),
        ("detail_page", DetailPageWorker),
        ("pdd_white_background", PinduoduoWhiteBackgroundWorker),
        ("social", SocialWorker),
    ]
    for output_type, worker_cls in worker_classes:
        if output_type not in sku.output_types:
            continue
        worker = worker_cls(
            client,
            model=effective_model,
            vector_store=vector_store,
        )
        r = await worker.run(
            sku,
            tenant_id,
            job_id,
            generation_context=generation_context,
            generation_mode=state.get("generation_mode", "standard"),
        )
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "generation_context": generation_context.model_dump(mode="json"),
        "logs": [f"image_worker finished {sku.sku_id} model={effective_model}"],
    }


def route_after_generation(state: JobState) -> str:
    failed = state.get("failed", [])
    if not failed:
        return "finalize_job"
    if state.get("retry_count", 0) >= 1:
        return "finalize_job"
    if any("生成图质量检查未通过" in (asset.error or "") for asset in failed):
        return "prepare_retry"
    return "finalize_job"


def prepare_retry(state: JobState) -> dict:
    retry_model = state.get("active_image_model") or "pro"
    error_text = " ".join(asset.error or "" for asset in state.get("failed", []))
    staged_keywords = ("融合", "穿着", "人体", "贴合", "服装", "上身")
    low_product_consistency = False
    low_garment_fusion = False
    for asset in state.get("failed", []):
        raw = asset.error or ""
        if "生成图质量检查未通过:" not in raw:
            continue
        try:
            audit = json.loads(raw.split(":", 1)[1].strip())
            if int(audit.get("product_consistency", 100)) < 85:
                low_product_consistency = True
            if int(audit.get("garment_fusion", 100)) < 80:
                low_garment_fusion = True
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    retry_mode = (
        "staged"
        if low_product_consistency
        or low_garment_fusion
        or any(word in error_text for word in staged_keywords)
        else "strict"
    )
    context = GenerationContext.model_validate(state["generation_context"])
    context.retry_count = state.get("retry_count", 0) + 1
    context.retry_mode = retry_mode
    return {
        "retry_count": context.retry_count,
        "generation_mode": retry_mode,
        "active_image_model": retry_model,
        "generation_context": context.model_dump(mode="json"),
        "completed": [],
        "failed": [],
        "logs": [f"quality retry selected mode={retry_mode} model={retry_model}"],
    }


async def video_worker(state: dict, config: RunnableConfig | None = None) -> dict:
    sku = _sku_from_state(state)
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    result = WorkerResult()

    if "video" in sku.output_types:
        worker = VeoWorker(client, model=state["video_model"])
        r = await worker.run(sku, tenant_id, job_id)
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "logs": [f"video_worker finished {sku.sku_id}"],
    }


async def finalize_job(state: JobState) -> dict:
    success_count = len(state.get("completed", []))
    fail_count = len(state.get("failed", []))

    if fail_count == 0:
        status = "done"
    elif success_count == 0:
        status = "failed"
    else:
        status = "partial_fail"

    return {"status": status}
