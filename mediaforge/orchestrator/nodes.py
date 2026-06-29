from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from mediaforge.config import get_settings
from mediaforge.db import AssetStatus, get_engine, get_redis
from mediaforge.db.job_store import JobStore
from mediaforge.models.job import SkuInput
from mediaforge.orchestrator.state import JobState
from mediaforge.rag.factory import get_vector_store
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image import DetailPageWorker, MainImageWorker, SocialWorker
from mediaforge.workers.openrouter_client import OpenRouterClient
from mediaforge.workers.video import VeoWorker


def validate_job(state: JobState) -> dict:
    if not state["skus"]:
        raise ValueError("No SKUs in batch")
    return {"total_sku_count": len(state["skus"])}


def fan_out(state: JobState) -> list[Send]:
    sends = []
    for raw_sku in state["skus"]:
        sku = SkuInput.model_validate(raw_sku) if isinstance(raw_sku, dict) else raw_sku
        image_types = {"main_image", "detail_page", "social"}
        if image_types.intersection(sku.output_types):
            sends.append(
                Send(
                    "image_worker",
                    {"sku": sku, "tenant_id": state["tenant_id"], "job_id": state["job_id"]},
                )
            )
        if "video" in sku.output_types:
            sends.append(
                Send(
                    "video_worker",
                    {"sku": sku, "tenant_id": state["tenant_id"], "job_id": state["job_id"]},
                )
            )
    return sends


async def image_worker(state: dict, config: RunnableConfig | None = None) -> dict:
    sku: SkuInput = (
        SkuInput.model_validate(state["sku"])
        if isinstance(state["sku"], dict)
        else state["sku"]
    )
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    result = WorkerResult()

    try:
        vector_store = get_vector_store()
    except Exception:
        vector_store = None

    worker_classes = [
        ("main_image", MainImageWorker),
        ("detail_page", DetailPageWorker),
        ("social", SocialWorker),
    ]
    for output_type, worker_cls in worker_classes:
        if output_type not in sku.output_types:
            continue
        worker = worker_cls(
            client,
            settings.output_dir,
            model=settings.default_image_model,
            vector_store=vector_store,
        )
        r = await worker.run(sku, tenant_id, job_id)
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "logs": [f"image_worker finished {sku.sku_id}"],
    }


async def video_worker(state: dict, config: RunnableConfig | None = None) -> dict:
    sku: SkuInput = (
        SkuInput.model_validate(state["sku"])
        if isinstance(state["sku"], dict)
        else state["sku"]
    )
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    result = WorkerResult()

    if "video" in sku.output_types:
        worker = VeoWorker(client, settings.output_dir, model=settings.default_video_model)
        r = await worker.run(sku, tenant_id, job_id)
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "logs": [f"video_worker finished {sku.sku_id}"],
    }


async def _persist_results(state: JobState) -> None:
    engine = get_engine()
    redis = await get_redis()
    store = JobStore(engine, redis)
    for asset in state.get("completed", []):
        await store.add_asset(
            job_id=state["job_id"],
            tenant_id=state["tenant_id"],
            sku_id=asset.sku_id,
            output_type=asset.output_type,
            model_used=asset.model_used,
            status=AssetStatus.success,
            file_path=asset.file_path,
            platform=asset.platform,
        )
    for asset in state.get("failed", []):
        await store.add_asset(
            job_id=state["job_id"],
            tenant_id=state["tenant_id"],
            sku_id=asset.sku_id,
            output_type=asset.output_type,
            model_used=asset.model_used,
            status=AssetStatus.failed,
            file_path=asset.file_path,
            platform=asset.platform,
            error_msg=asset.error or "unknown",
        )
    await store.finalize_job(state["job_id"], len(state.get("completed", [])), len(state.get("failed", [])))


async def finalize_job(state: JobState) -> dict:
    await _persist_results(state)

    success_count = len(state.get("completed", []))
    fail_count = len(state.get("failed", []))

    if fail_count == 0:
        status = "done"
    elif success_count == 0:
        status = "failed"
    else:
        status = "partial_fail"

    return {"status": status}
