import asyncio

from celery import Task
from celery.utils.log import get_task_logger
from loguru import logger as loguru_logger

from mediaforge.celery_app import celery_app
from mediaforge.config import get_settings

_task_logger = get_task_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task.

    asyncio.run() creates and tears down a fresh event loop. Any pooled
    resources (DB engines, httpx clients) bound to that loop must be
    released before it closes, or subsequent tasks will see zombie
    connections and Postgres will exhaust max_connections.
    """

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


@celery_app.task(
    bind=True,
    name="mediaforge.orchestrator.tasks.process_job",
    max_retries=None,   # use per-call retry control
    acks_late=True,
)
def process_job(self: Task, job_id: str, tenant_id: str, skus: list) -> dict:
    """Process a single batch job: run LangGraph pipeline and persist results."""
    settings = get_settings()
    _task_logger.info("Processing job_id=%s tenant=%s skus=%d", job_id, tenant_id, len(skus))

    async def _run():
        from mediaforge.db.engine import get_engine
        from mediaforge.db.redis_client import get_redis
        from mediaforge.db.job_store import JobStore
        from mediaforge.orchestrator.batch_graph import build_batch_graph
        from mediaforge.orchestrator.state import JobState

        engine = get_engine()
        redis = await get_redis()
        store = JobStore(engine, redis)
        graph = await build_batch_graph()

        await store.start_job(job_id)

        initial = JobState(
            job_id=job_id,
            tenant_id=tenant_id,
            skus=skus,
            total_sku_count=len(skus),
            status="running",
        )
        await graph.ainvoke(initial, config={"configurable": {"thread_id": job_id}})
        return {"job_id": job_id, "status": "done"}

    try:
        return _run_async(_run())
    except Exception as exc:
        _task_logger.exception("Job failed job_id=%s: %s", job_id, exc)

        async def _fail():
            from mediaforge.db.engine import get_engine
            from mediaforge.db.redis_client import get_redis
            from mediaforge.db.job_store import JobStore
            engine = get_engine()
            redis = await get_redis()
            store = JobStore(engine, redis)
            await store.finalize_job(job_id, success=0, failed=len(skus))

        try:
            _run_async(_fail())
        except Exception:
            pass

        retry_in = settings.celery_retry_backoff * (2 ** self.request.retries)
        if self.request.retries < settings.celery_max_retries:
            raise self.retry(exc=exc, countdown=retry_in)
        raise
