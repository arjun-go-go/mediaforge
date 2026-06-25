import json
import uuid
from datetime import datetime, timezone

from loguru import logger

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import AssetStatus, AssetTable, JobTable
from mediaforge.models.job import BatchSubmitPayload



def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class JobStore:
    def __init__(self, engine: AsyncEngine, redis: Redis):
        self.engine = engine
        self.redis = redis

    async def create_job(self, tenant_id: str, payload: BatchSubmitPayload) -> str:
        job_id = uuid.uuid4()
        async with self.engine.connect() as conn:
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
            await conn.commit()
        return str(job_id)

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
        asset_id = uuid.uuid4()
        async with self.engine.connect() as conn:
            await conn.execute(
                AssetTable.__table__.insert().values(
                    asset_id=asset_id,
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
            )
            await conn.commit()
        return str(asset_id)

    async def get_assets_for_job(self, job_id: str) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(AssetTable.__table__).where(
                    AssetTable.__table__.c.job_id == _as_uuid(job_id)
                )
            )
            return [dict(row) for row in result.mappings().all()]

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
