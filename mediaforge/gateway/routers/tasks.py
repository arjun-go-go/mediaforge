import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from mediaforge.db.job_store import JobStore
from mediaforge.gateway.dependencies import get_job_store, get_redis_client, get_tenant_only
from mediaforge.models.tenant import Tenant

router = APIRouter(prefix="/api/v1/tasks")


@router.get("")
async def list_tasks(
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
    limit: int = Query(50, ge=1, le=100),
):
    try:
        jobs = await store.list_jobs_for_tenant(str(tenant.tenant_id), limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant ID") from exc
    return {
        "jobs": [
            {
                "job_id": str(job["job_id"]),
                "status": job["status"],
                "total_skus": job["total_skus"],
                "done_skus": job["done_skus"],
                "created_at": job["created_at"].isoformat() if job["created_at"] else None,
            }
            for job in jobs
        ]
    }


@router.get("/{job_id}")
async def get_task(
    job_id: str,
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
):
    job = await store.get_job(job_id)
    if str(job["tenant_id"]) != str(tenant.tenant_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    assets = await store.get_assets_for_job(job_id)

    for asset in assets:
        fp = asset.get("file_path")
        if fp and not str(fp).startswith(("http://", "https://", "/")):
            asset["file_path"] = f"/outputs/{fp}"

    return {
        "job_id": job_id,
        "status": job["status"],
        "total_skus": job["total_skus"],
        "done_skus": job["done_skus"],
        "input_data": job.get("input_data"),
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
        "finished_at": job["finished_at"].isoformat() if job.get("finished_at") else None,
        "assets": assets,
    }


@router.get("/{job_id}/stream")
async def stream_task(
    job_id: str,
    request: Request,
    tenant: Tenant = Depends(get_tenant_only),
    redis: Redis = Depends(get_redis_client),
):
    _MAX_DURATION = 30 * 60  # 30 minutes hard cutoff

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        start = asyncio.get_running_loop().time()
        last_keepalive = start
        try:
            while True:
                now = asyncio.get_running_loop().time()
                if now - start > _MAX_DURATION:
                    yield "event: timeout\ndata: {}\n\n"
                    break
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message["data"]
                    yield f"event: progress\ndata: {data}\n\n"
                    parsed = json.loads(data)
                    if parsed.get("event") == "done":
                        break
                elif now - last_keepalive >= 15:
                    yield ": keepalive\n\n"
                    last_keepalive = now
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(f"job:{job_id}")
            await pubsub.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


_TERMINAL_STATUSES = {"done", "failed", "partial_fail"}


@router.delete("/failed")
async def delete_failed_tasks(
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
):
    """Delete all failed jobs for the current tenant. Returns the deleted count."""
    jobs = await store.list_jobs_for_tenant(str(tenant.tenant_id), limit=1000)
    deleted = 0
    for job in jobs:
        if job["status"] == "failed":
            deleted += await store.delete_job(str(job["job_id"]))
    return {"deleted": deleted}


@router.delete("/{job_id}")
async def delete_task(
    job_id: str,
    tenant: Tenant = Depends(get_tenant_only),
    store: JobStore = Depends(get_job_store),
):
    """Delete a job. Only terminal-state jobs can be deleted to avoid killing
    running tasks."""
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(job["tenant_id"]) != str(tenant.tenant_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if job["status"] not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete job in status '{job['status']}'; wait for it to finish.",
        )
    deleted = await store.delete_job(job_id)
    return {"deleted": deleted}
