from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from mediaforge.db.job_store import JobStore
from mediaforge.gateway.dependencies import get_job_store, get_tenant_only
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.job import BatchSubmitPayload
from mediaforge.models.tenant import Tenant
from mediaforge.orchestrator.dispatcher import dispatch_generation_job

router = APIRouter(prefix="/api/v1/batch")


@router.post("/submit")
@limiter.limit("10/minute")
async def submit_batch(
    request: Request,
    payload: BatchSubmitPayload,
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
):
    job_id = await dispatch_generation_job(tenant, payload, store)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "running"})
