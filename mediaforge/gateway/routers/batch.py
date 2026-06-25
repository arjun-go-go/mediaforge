from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from mediaforge.auth.tenant import TenantResolver
from mediaforge.db.job_store import JobStore
from mediaforge.gateway.dependencies import get_job_store, get_redis_client, get_tenant_only
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.job import BatchSubmitPayload
from mediaforge.models.tenant import Tenant
from mediaforge.observability.cost_tracker import CostTracker
from mediaforge.orchestrator.tasks import process_job
from mediaforge.workers.openrouter_client import get_image_models

router = APIRouter(prefix="/api/v1/batch")


@router.post("/submit")
@limiter.limit("10/minute")
async def submit_batch(
    request: Request,
    payload: BatchSubmitPayload,
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
    redis=Depends(get_redis_client),
):
    resolver = TenantResolver()
    resolver.check_quota(tenant, payload.total_skus)
    resolver.check_model_allowed(tenant, payload.image_model.value)
    resolver.check_model_allowed(tenant, payload.video_model.value)

    tenant_id_str = str(tenant.tenant_id)
    job_id = await store.create_job(tenant_id=tenant_id_str, payload=payload)

    tracker = CostTracker()
    model_name = get_image_models().get(payload.image_model.value, payload.image_model.value)
    await tracker.record(tenant_id_str, job_id, [{"model": model_name, "count": payload.total_skus}])

    skus_data = [s.model_dump(mode="json") for s in payload.skus]
    queue = payload.priority  # "high" | "normal" | "low"
    process_job.apply_async(
        args=[job_id, tenant_id_str, skus_data],
        queue=queue,
        routing_key=queue,
    )

    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "pending"})
