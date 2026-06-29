"""Maintenance Celery tasks — run by Celery Beat on a schedule."""

from loguru import logger

from mediaforge.celery_app import celery_app
from mediaforge.orchestrator.tasks import _run_async


@celery_app.task(name="mediaforge.orchestrator.maintenance.purge_expired_tokens", bind=True)
def purge_expired_tokens(self):
    """Delete refresh tokens whose expires_at is in the past."""
    async def _purge():
        from mediaforge.db.engine import get_engine
        from mediaforge.db.refresh_token_store import RefreshTokenStore
        store = RefreshTokenStore(get_engine())
        count = await store.purge_expired()
        logger.info("Maintenance: purged {} expired refresh tokens", count)
        return count

    try:
        return _run_async(_purge())
    except Exception as exc:
        logger.error("purge_expired_tokens failed: {}", exc)
        return 0


@celery_app.task(name="mediaforge.orchestrator.maintenance.purge_old_audit_logs", bind=True)
def purge_old_audit_logs(self):
    """Delete audit log entries older than 90 days, in batches of 1000."""
    async def _purge():
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import delete, select
        from mediaforge.db.engine import get_engine
        from mediaforge.db.tables import AuditLogTable

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        tbl = AuditLogTable.__table__
        engine = get_engine()
        total = 0
        async with engine.connect() as conn:
            while True:
                batch_ids = await conn.execute(
                    select(tbl.c.log_id).where(tbl.c.created_at < cutoff).limit(1000)
                )
                ids = [row[0] for row in batch_ids.fetchall()]
                if not ids:
                    break
                await conn.execute(delete(tbl).where(tbl.c.log_id.in_(ids)))
                await conn.commit()
                total += len(ids)
        logger.info("Maintenance: purged {} audit log entries older than 90d", total)
        return total

    try:
        return _run_async(_purge())
    except Exception as exc:
        logger.error("purge_old_audit_logs failed: {}", exc)
        return 0
