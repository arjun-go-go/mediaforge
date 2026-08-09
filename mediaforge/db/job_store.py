import json
import uuid
from datetime import datetime, timezone

from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import AssetStatus, AssetTable, JobItemTable, JobTable
from mediaforge.models.job import BatchSubmitPayload


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class JobStore:
    def __init__(self, engine: AsyncEngine, redis: Redis):
        self.engine = engine
        self.redis = redis

    async def create_job(self, tenant_id: str, payload: BatchSubmitPayload) -> str:
        job_id = uuid.uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                JobTable.__table__.insert().values(
                    job_id=job_id,
                    tenant_id=_as_uuid(tenant_id),
                    status="pending",
                    total_skus=payload.total_skus,
                    input_data=payload.model_dump(mode="json"),
                    created_at=datetime.now(timezone.utc),
                )
            )
            await conn.execute(
                JobItemTable.__table__.insert(),
                [
                    {
                        "job_id": job_id,
                        "sku_id": sku.sku_id,
                        "status": "pending",
                        "updated_at": datetime.now(timezone.utc),
                    }
                    for sku in payload.skus
                ],
            )
        return str(job_id)

    async def create_job_idempotent(
        self,
        tenant_id: str,
        payload: BatchSubmitPayload,
        *,
        idempotency_key: str,
        created_by: str | None = None,
        source: str = "agent",
    ) -> tuple[str, bool]:
        """Create one job once; return (job_id, was_created)."""
        tenant_uuid = _as_uuid(tenant_id)
        job_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        async with self.engine.begin() as conn:
            inserted = (
                await conn.execute(
                    pg_insert(JobTable.__table__)
                    .values(
                        job_id=job_id,
                        tenant_id=tenant_uuid,
                        created_by=_as_uuid(created_by) if created_by else None,
                        source=source,
                        idempotency_key=idempotency_key,
                        status="pending",
                        total_skus=payload.total_skus,
                        input_data=payload.model_dump(mode="json"),
                        created_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["tenant_id", "idempotency_key"],
                        index_where=JobTable.__table__.c.idempotency_key.isnot(None),
                    )
                    .returning(JobTable.__table__.c.job_id)
                )
            ).scalar_one_or_none()
            if inserted is None:
                existing = (
                    await conn.execute(
                        select(JobTable.__table__.c.job_id).where(
                            JobTable.__table__.c.tenant_id == tenant_uuid,
                            JobTable.__table__.c.idempotency_key == idempotency_key,
                        )
                    )
                ).scalar_one()
                return str(existing), False
            await conn.execute(
                JobItemTable.__table__.insert(),
                [
                    {
                        "job_id": job_id,
                        "sku_id": sku.sku_id,
                        "status": "pending",
                        "updated_at": now,
                    }
                    for sku in payload.skus
                ],
            )
        return str(job_id), True

    async def get_job_by_idempotency(self, tenant_id: str, idempotency_key: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    select(JobTable.__table__).where(
                        JobTable.__table__.c.tenant_id == _as_uuid(tenant_id),
                        JobTable.__table__.c.idempotency_key == idempotency_key,
                    )
                )
            ).mappings().first()
            return dict(row) if row else None

    async def get_job(self, job_id: str) -> dict:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(JobTable.__table__).where(JobTable.__table__.c.job_id == _as_uuid(job_id))
            )
            row = result.mappings().first()
            if row is None:
                raise ValueError(f"Job {job_id} not found")
            return dict(row)

    async def list_jobs_for_tenant(self, tenant_id: str, limit: int = 50) -> list[dict]:
        tenant_uuid = _as_uuid(tenant_id)
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(
                    JobTable.__table__.c.job_id,
                    JobTable.__table__.c.status,
                    JobTable.__table__.c.total_skus,
                    JobTable.__table__.c.done_skus,
                    JobTable.__table__.c.created_at,
                )
                .where(JobTable.__table__.c.tenant_id == tenant_uuid)
                .order_by(JobTable.__table__.c.created_at.desc())
                .limit(limit)
            )
            return [dict(row) for row in result.mappings().all()]

    async def start_job(self, job_id: str) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                update(JobTable.__table__)
                .where(JobTable.__table__.c.job_id == _as_uuid(job_id))
                .values(status="running", started_at=datetime.now(timezone.utc))
            )
            await conn.commit()

    async def start_job_item(self, job_id: str, sku_id: str) -> bool:
        """Mark one SKU running. Terminal items are idempotently skipped."""
        table = JobItemTable.__table__
        async with self.engine.begin() as conn:
            current = (
                await conn.execute(
                    select(table.c.status).where(
                        table.c.job_id == _as_uuid(job_id), table.c.sku_id == sku_id
                    )
                )
            ).scalar_one()
            if current in {"done", "partial_fail", "failed"}:
                return False
            await conn.execute(
                update(table)
                .where(table.c.job_id == _as_uuid(job_id), table.c.sku_id == sku_id)
                .values(status="running", error_msg=None, updated_at=datetime.now(timezone.utc))
            )
        return True

    async def complete_job_item(
        self,
        job_id: str,
        sku_id: str,
        *,
        completed_assets: int,
        failed_assets: int,
        error_msg: str | None = None,
    ) -> dict:
        if failed_assets == 0:
            status = "done"
        elif completed_assets == 0:
            status = "failed"
        else:
            status = "partial_fail"
        table = JobItemTable.__table__
        async with self.engine.begin() as conn:
            await conn.execute(
                update(table)
                .where(table.c.job_id == _as_uuid(job_id), table.c.sku_id == sku_id)
                .values(
                    status=status,
                    completed_assets=completed_assets,
                    failed_assets=failed_assets,
                    error_msg=error_msg,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        return await self.refresh_job_progress(job_id)

    async def mark_job_item_retrying(self, job_id: str, sku_id: str, error_msg: str) -> None:
        table = JobItemTable.__table__
        async with self.engine.begin() as conn:
            await conn.execute(
                update(table)
                .where(table.c.job_id == _as_uuid(job_id), table.c.sku_id == sku_id)
                .values(
                    status="retrying",
                    error_msg=error_msg,
                    updated_at=datetime.now(timezone.utc),
                )
            )

    async def save_job_item_context(
        self, job_id: str, sku_id: str, generation_context: dict
    ) -> None:
        table = JobItemTable.__table__
        async with self.engine.begin() as conn:
            await conn.execute(
                update(table)
                .where(table.c.job_id == _as_uuid(job_id), table.c.sku_id == sku_id)
                .values(
                    generation_context=generation_context,
                    updated_at=datetime.now(timezone.utc),
                )
            )

    async def get_job_items(self, job_id: str) -> list[dict]:
        table = JobItemTable.__table__
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                select(table).where(table.c.job_id == _as_uuid(job_id))
            )
            return [dict(row) for row in rows.mappings().all()]

    async def refresh_job_progress(self, job_id: str) -> dict:
        item = JobItemTable.__table__
        job = JobTable.__table__
        job_uuid = _as_uuid(job_id)
        terminal = ["done", "partial_fail", "failed"]
        async with self.engine.begin() as conn:
            counts = (
                await conn.execute(
                    select(
                        func.count().label("total_skus"),
                        func.count().filter(item.c.status.in_(terminal)).label("done_skus"),
                        func.count().filter(item.c.status == "failed").label("failed_skus"),
                        func.count().filter(item.c.status == "partial_fail").label("partial_skus"),
                        func.coalesce(func.sum(item.c.completed_assets), 0).label("completed_assets"),
                        func.coalesce(func.sum(item.c.failed_assets), 0).label("failed_assets"),
                    ).where(item.c.job_id == job_uuid)
                )
            ).mappings().one()
            total = int(counts["total_skus"])
            done = int(counts["done_skus"])
            if done < total:
                status = "running"
                finished_at = None
            elif int(counts["failed_skus"]) == total:
                status = "failed"
                finished_at = datetime.now(timezone.utc)
            elif int(counts["failed_skus"]) or int(counts["partial_skus"]):
                status = "partial_fail"
                finished_at = datetime.now(timezone.utc)
            else:
                status = "done"
                finished_at = datetime.now(timezone.utc)
            await conn.execute(
                update(job)
                .where(job.c.job_id == job_uuid)
                .values(status=status, done_skus=done, finished_at=finished_at)
            )

        event = {
            "event": "done" if done == total else "progress",
            "job_id": job_id,
            "status": status,
            "done_skus": done,
            "total_skus": total,
            "completed_assets": int(counts["completed_assets"]),
            "failed_assets": int(counts["failed_assets"]),
        }
        try:
            await self.redis.publish(f"job:{job_id}", json.dumps(event))
        except Exception:
            logger.warning("Failed to publish job progress for {}", job_id, exc_info=True)
        return event

    async def add_asset(
        self,
        *,
        job_id: str,
        tenant_id: str,
        sku_id: str,
        output_type: str,
        model_used: str,
        status: AssetStatus,
        file_path: str | None = None,
        platform: str | None = None,
        error_msg: str | None = None,
    ) -> str:
        table = AssetTable.__table__
        platform_match = table.c.platform.is_(None) if platform is None else table.c.platform == platform
        async with self.engine.begin() as conn:
            existing = (
                await conn.execute(
                    select(table.c.asset_id).where(
                        table.c.job_id == _as_uuid(job_id),
                        table.c.sku_id == sku_id,
                        table.c.output_type == output_type,
                        platform_match,
                        table.c.status == AssetStatus.success,
                    )
                )
            ).scalar_one_or_none()
            values = dict(
                    job_id=_as_uuid(job_id),
                    tenant_id=_as_uuid(tenant_id),
                    sku_id=sku_id,
                    output_type=output_type,
                    platform=platform,
                    model_used=model_used,
                    file_path=file_path,
                    status=status,
                    error_msg=error_msg,
                )
            if status == AssetStatus.success and existing:
                await conn.execute(update(table).where(table.c.asset_id == existing).values(**values))
                return str(existing)
            asset_id = uuid.uuid4()
            values["asset_id"] = asset_id
            await conn.execute(table.insert().values(**values))
        return str(asset_id)

    async def get_assets_for_job(self, job_id: str) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(AssetTable.__table__).where(
                    AssetTable.__table__.c.job_id == _as_uuid(job_id)
                )
            )
            return [dict(row) for row in result.mappings().all()]

    async def get_asset(
        self, job_id: str, sku_id: str, output_type: str, platform: str | None
    ) -> dict | None:
        table = AssetTable.__table__
        platform_match = table.c.platform.is_(None) if platform is None else table.c.platform == platform
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    select(table).where(
                        table.c.job_id == _as_uuid(job_id),
                        table.c.sku_id == sku_id,
                        table.c.output_type == output_type,
                        platform_match,
                        table.c.status == AssetStatus.success,
                    )
                )
            ).mappings().first()
        return dict(row) if row else None

    async def finalize_job(self, job_id: str, success: int, failed: int) -> str:
        status = "done" if failed == 0 else ("failed" if success == 0 else "partial_fail")
        async with self.engine.connect() as conn:
            await conn.execute(
                update(JobTable.__table__)
                .where(JobTable.__table__.c.job_id == _as_uuid(job_id))
                .values(
                    status=status,
                    done_skus=success,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()
        event = {
            "event": "done",
            "job_id": job_id,
            "status": status,
            "success": success,
            "failed": failed,
        }
        try:
            await self.redis.publish(f"job:{job_id}", json.dumps(event))
        except Exception:
            logger.warning("Failed to publish job completion event for {}", job_id, exc_info=True)
        return status

    async def delete_job(self, job_id: str) -> int:
        """Delete a job and all its assets. Returns number of jobs deleted (0 or 1)."""
        job_uuid = _as_uuid(job_id)
        async with self.engine.begin() as conn:
            await conn.execute(
                delete(AssetTable.__table__).where(AssetTable.__table__.c.job_id == job_uuid)
            )
            result = await conn.execute(
                delete(JobTable.__table__).where(JobTable.__table__.c.job_id == job_uuid)
            )
        return result.rowcount
