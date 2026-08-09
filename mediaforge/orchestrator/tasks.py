import asyncio

from celery import Task
from celery.utils.log import get_task_logger

from mediaforge.celery_app import celery_app
from mediaforge.config import get_settings

_task_logger = get_task_logger(__name__)


def _run_async(coro):
    """Run one async SKU pipeline inside a synchronous Celery task."""

    async def _wrapped():
        try:
            return await coro
        finally:
            from mediaforge.db.engine import close_engine
            from mediaforge.http_clients import close_clients

            try:
                await close_engine()
            except Exception:
                pass
            try:
                await close_clients()
            except Exception:
                pass

    return asyncio.run(_wrapped())


async def _get_store():
    from mediaforge.db.engine import get_engine
    from mediaforge.db.job_store import JobStore
    from mediaforge.db.redis_client import get_redis

    return JobStore(get_engine(), await get_redis())


@celery_app.task(
    bind=True,
    name="mediaforge.orchestrator.tasks.process_sku",
    max_retries=None,
    acks_late=True,
)
def process_sku(
    self: Task,
    job_id: str,
    tenant_id: str,
    sku_data: dict,
    image_model: str,
    video_model: str,
) -> dict:
    """Process exactly one SKU so retries never replay an entire batch."""
    settings = get_settings()
    sku_id = str(sku_data["sku_id"])
    _task_logger.info("Processing job_id=%s sku=%s", job_id, sku_id)

    async def _run():
        from mediaforge.db.tables import AssetStatus
        from mediaforge.models.job import AssetOutput
        from mediaforge.orchestrator.batch_graph import build_batch_graph
        from mediaforge.orchestrator.state import JobState

        store = await _get_store()
        if not await store.start_job_item(job_id, sku_id):
            return {"job_id": job_id, "sku_id": sku_id, "status": "skipped"}

        graph = await build_batch_graph()
        initial = JobState(
            job_id=job_id,
            tenant_id=tenant_id,
            skus=[sku_data],
            total_sku_count=1,
            image_model=image_model,
            active_image_model=image_model,
            video_model=video_model,
            completed=[],
            failed=[],
            logs=[],
            generation_context={},
            generation_mode="standard",
            retry_count=0,
            status="running",
        )
        result = await graph.ainvoke(initial)
        completed = [AssetOutput.model_validate(asset) for asset in result.get("completed", [])]
        failed = [AssetOutput.model_validate(asset) for asset in result.get("failed", [])]
        await store.save_job_item_context(
            job_id, sku_id, result.get("generation_context", {})
        )

        for asset in completed:
            await store.add_asset(
                job_id=job_id,
                tenant_id=tenant_id,
                sku_id=asset.sku_id,
                output_type=asset.output_type,
                model_used=asset.model_used,
                status=AssetStatus.success,
                file_path=asset.file_path,
                platform=asset.platform,
            )
        for asset in failed:
            await store.add_asset(
                job_id=job_id,
                tenant_id=tenant_id,
                sku_id=asset.sku_id,
                output_type=asset.output_type,
                model_used=asset.model_used,
                status=AssetStatus.failed,
                file_path=asset.file_path,
                platform=asset.platform,
                error_msg=asset.error or "unknown",
            )

        progress = await store.complete_job_item(
            job_id,
            sku_id,
            completed_assets=len(completed),
            failed_assets=len(failed),
            error_msg=failed[0].error if failed else None,
        )
        return {"job_id": job_id, "sku_id": sku_id, "status": progress["status"]}

    try:
        return _run_async(_run())
    except Exception as exc:
        _task_logger.exception("SKU failed job_id=%s sku=%s: %s", job_id, sku_id, exc)
        error_message = str(exc)
        retry_in = settings.celery_retry_backoff * (2 ** self.request.retries)

        async def _record_retry(final: bool):
            store = await _get_store()
            if final:
                await store.complete_job_item(
                    job_id,
                    sku_id,
                    completed_assets=0,
                    failed_assets=1,
                    error_msg=error_message,
                )
            else:
                await store.mark_job_item_retrying(job_id, sku_id, error_message)
                await store.refresh_job_progress(job_id)

        final = self.request.retries >= settings.celery_max_retries
        try:
            _run_async(_record_retry(final))
        except Exception:
            _task_logger.exception("Failed to persist retry state job_id=%s sku=%s", job_id, sku_id)
        if not final:
            raise self.retry(exc=exc, countdown=retry_in)
        raise
