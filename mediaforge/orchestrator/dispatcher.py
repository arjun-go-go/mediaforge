from mediaforge.auth.tenant import TenantResolver
from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.redis_client import get_redis
from mediaforge.models.job import BatchSubmitPayload
from mediaforge.models.tenant import Tenant
from mediaforge.observability.cost_tracker import CostTracker
from mediaforge.orchestrator.tasks import process_sku
from mediaforge.workers.openrouter_client import get_image_models


async def dispatch_generation_job(
    tenant: Tenant,
    payload: BatchSubmitPayload,
    store: JobStore | None = None,
    *,
    idempotency_key: str | None = None,
    created_by: str | None = None,
    source: str = "batch",
) -> str:
    """Create and dispatch one durable batch job from API or Agent."""
    resolver = TenantResolver()
    resolver.check_quota(tenant, payload.total_skus)
    requested_outputs = {output for sku in payload.skus for output in sku.output_types}
    if requested_outputs.intersection(
        {"main_image", "detail_page", "pdd_white_background", "social"}
    ):
        resolver.check_model_allowed(tenant, payload.image_model.value)
    if "video" in requested_outputs:
        resolver.check_model_allowed(tenant, payload.video_model.value)

    if store is None:
        store = JobStore(get_engine(), await get_redis())
    tenant_id = str(tenant.tenant_id)
    created = True
    if idempotency_key:
        job_id, created = await store.create_job_idempotent(
            tenant_id,
            payload,
            idempotency_key=idempotency_key,
            created_by=created_by,
            source=source,
        )
    else:
        job_id = await store.create_job(tenant_id=tenant_id, payload=payload)

    if not created:
        return job_id

    model_name = get_image_models().get(payload.image_model.value, payload.image_model.value)
    await CostTracker().record(
        tenant_id, job_id, [{"model": model_name, "count": payload.total_skus}]
    )

    await store.start_job(job_id)
    queue = payload.priority
    for sku in payload.skus:
        process_sku.apply_async(
            args=[
                job_id,
                tenant_id,
                sku.model_dump(mode="json"),
                payload.image_model.value,
                payload.video_model.value,
            ],
            queue=queue,
            routing_key=queue,
        )
    return job_id
