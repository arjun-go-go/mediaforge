import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import func, or_, select

from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.tables import AssetTable, JobItemTable, JobTable, ProductTable
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


@router.get("/overview")
async def task_overview(
    tenant: Tenant = Depends(get_tenant_only),
):
    """Action-oriented dashboard data for the current tenant."""
    job = JobTable.__table__
    asset = AssetTable.__table__
    item = JobItemTable.__table__
    since = datetime.now(timezone.utc) - timedelta(days=7)
    async with get_engine().connect() as connection:
        jobs = (
            await connection.execute(
                select(job)
                .where(job.c.tenant_id == tenant.tenant_id)
                .order_by(job.c.created_at.desc())
                .limit(100)
            )
        ).mappings().all()
        recent_assets = (
            await connection.execute(
                select(asset)
                .where(
                    asset.c.tenant_id == tenant.tenant_id,
                    asset.c.status == "success",
                    asset.c.file_path.isnot(None),
                )
                .order_by(asset.c.created_at.desc())
                .limit(12)
            )
        ).mappings().all()
        seven_day_assets = int(
            (
                await connection.execute(
                    select(func.count()).select_from(asset).where(
                        asset.c.tenant_id == tenant.tenant_id,
                        asset.c.created_at >= since,
                        asset.c.status == "success",
                    )
                )
            ).scalar_one()
        )
        contexts = (
            await connection.execute(
                select(item.c.generation_context)
                .select_from(item.join(job, item.c.job_id == job.c.job_id))
                .where(job.c.tenant_id == tenant.tenant_id, item.c.updated_at >= since)
            )
        ).scalars().all()
        asset_stats = (
            await connection.execute(
                select(
                    asset.c.model_used,
                    asset.c.platform,
                    asset.c.status,
                    func.count().label("count"),
                )
                .where(asset.c.tenant_id == tenant.tenant_id, asset.c.created_at >= since)
                .group_by(asset.c.model_used, asset.c.platform, asset.c.status)
            )
        ).mappings().all()

    quality_results = [
        result
        for context in contexts
        for result in ((context or {}).get("quality_results") or [])
        if "passed" in result and result.get("asset", "").split(":")[-1] != "detail_set"
    ]
    quality_pass_rate = (
        round(sum(1 for result in quality_results if result.get("passed")) * 100 / len(quality_results))
        if quality_results
        else None
    )
    durations = [
        (row["finished_at"] - row["started_at"]).total_seconds()
        for row in jobs
        if row["started_at"] and row["finished_at"] and row["created_at"] >= since
    ]
    model_totals: dict[str, dict[str, int]] = {}
    platform_totals: dict[str, int] = {}
    estimated_cost_usd = 0.0
    from mediaforge.observability.cost_tracker import CostTracker

    rates = CostTracker.MODEL_RATES
    for row in asset_stats:
        model = row["model_used"]
        count = int(row["count"])
        bucket = model_totals.setdefault(model, {"total": 0, "success": 0})
        bucket["total"] += count
        if str(row["status"]) == "success":
            bucket["success"] += count
            platform = str(row["platform"] or "unknown").split(":", 1)[0]
            platform_totals[platform] = platform_totals.get(platform, 0) + count
        model_rate = rates.get(model, {})
        estimated_cost_usd += count * float(model_rate.get("per_image", model_rate.get("per_video", 0.0)))

    reference_counts: dict[str, int] = {}
    for row in jobs:
        if not row["created_at"] or row["created_at"] < since:
            continue
        for sku in (row.get("input_data") or {}).get("skus") or []:
            reference = sku.get("ref_sku_id")
            if reference:
                reference_counts[reference] = reference_counts.get(reference, 0) + 1

    def job_summary(row):
        payload = row.get("input_data") or {}
        skus = payload.get("skus") or []
        first = skus[0] if skus else {}
        return {
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "total_skus": row["total_skus"],
            "done_skus": row["done_skus"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "product_name": first.get("product_name") or first.get("sku_id") or "未命名商品",
            "sku_id": first.get("sku_id") or "",
            "product_image_url": first.get("product_image_url") or "",
            "platforms": first.get("target_platforms") or [],
        }

    return {
        "active_jobs": [job_summary(row) for row in jobs if str(row["status"]) in {"pending", "running"}],
        "attention_jobs": [job_summary(row) for row in jobs if str(row["status"]) in {"failed", "partial_fail"}][:8],
        "recent_jobs": [job_summary(row) for row in jobs[:10]],
        "recent_assets": [
            {
                "asset_id": str(row["asset_id"]),
                "job_id": str(row["job_id"]),
                "sku_id": row["sku_id"],
                "output_type": row["output_type"],
                "platform": row["platform"],
                "file_path": row["file_path"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in recent_assets
        ],
        "metrics": {
            "generated_assets_7d": seven_day_assets,
            "quality_pass_rate_7d": quality_pass_rate,
            "average_duration_seconds_7d": round(sum(durations) / len(durations)) if durations else None,
            "active_jobs": sum(1 for row in jobs if str(row["status"]) in {"pending", "running"}),
        },
        "analytics": {
            "estimated_cost_usd_7d": round(estimated_cost_usd, 2),
            "platforms": [
                {"name": name, "count": count}
                for name, count in sorted(platform_totals.items(), key=lambda item: item[1], reverse=True)
            ],
            "models": [
                {
                    "name": name,
                    "total": values["total"],
                    "success_rate": round(values["success"] * 100 / values["total"]) if values["total"] else 0,
                }
                for name, values in sorted(model_totals.items(), key=lambda item: item[1]["total"], reverse=True)
            ],
            "references": [
                {"sku_id": sku_id, "count": count}
                for sku_id, count in sorted(reference_counts.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
        },
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
    job_items = await store.get_job_items(job_id)
    input_data = job.get("input_data") or {}
    ref_sku_ids = {
        sku.get("ref_sku_id")
        for sku in input_data.get("skus", [])
        if sku.get("ref_sku_id")
    }
    reference_products = {}
    if ref_sku_ids:
        table = ProductTable.__table__
        visible = or_(table.c.visibility == "global", table.c.tenant_id == tenant.tenant_id)
        async with get_engine().connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        table.c.sku_code,
                        table.c.image_url,
                        table.c.description,
                        table.c.category,
                    ).where(visible, table.c.sku_code.in_(ref_sku_ids))
                )
            ).mappings()
            for row in rows:
                reference_products[row["sku_code"]] = dict(row)

    return {
        "job_id": job_id,
        "status": job["status"],
        "total_skus": job["total_skus"],
        "done_skus": job["done_skus"],
        "input_data": input_data,
        "reference_products": reference_products,
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
        "finished_at": job["finished_at"].isoformat() if job.get("finished_at") else None,
        "assets": assets,
        "job_items": job_items,
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
