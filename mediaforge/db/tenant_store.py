"""Tenant persistence helpers.

Uses SQLAlchemy Core (Table-level insert/select) to match the convention
established in `job_store.py`. The returned `Tenant` Pydantic models are
detached from any ORM session, so they are safe to pass around.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import TenantTable
from mediaforge.models.tenant import Tenant, TenantPlan, TenantQuota

_tenant_tbl = TenantTable.__table__


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _row_to_tenant(row) -> Tenant:
    quotas_data = dict(row["quotas"] or {})
    plan = TenantPlan(row["plan"])
    # Stored quotas JSON always includes `plan`; if missing (legacy rows), inject it.
    quotas_data.setdefault("plan", plan.value)
    quotas = TenantQuota(**quotas_data) if quotas_data else TenantQuota(plan=plan)
    return Tenant(
        tenant_id=row["tenant_id"],
        name=row["name"],
        api_key_hash=row["api_key_hash"] or "",
        plan=plan,
        quotas=quotas,
    )


class TenantStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def get_by_id(self, tenant_id: str | uuid.UUID) -> Tenant | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_tenant_tbl).where(_tenant_tbl.c.tenant_id == _as_uuid(tenant_id))
            )
            row = result.mappings().first()
        if row is None:
            return None
        return _row_to_tenant(row)

    async def list_tenants(self) -> list[Tenant]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_tenant_tbl).order_by(_tenant_tbl.c.created_at.asc())
            )
            rows = result.mappings().all()
        return [_row_to_tenant(r) for r in rows]

    async def create(self, *, name: str, plan: TenantPlan, tenant_id: uuid.UUID | None = None) -> Tenant:
        tid = tenant_id or uuid.uuid4()
        quotas = TenantQuota(plan=plan)
        async with self.engine.connect() as conn:
            await conn.execute(
                insert(_tenant_tbl).values(
                    tenant_id=tid,
                    name=name,
                    api_key_hash="",
                    plan=plan.value,
                    quotas=quotas.model_dump(mode="json"),
                    created_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()
        return Tenant(
            tenant_id=tid,
            name=name,
            api_key_hash="",
            plan=plan,
            quotas=quotas,
        )

    async def exists(self, tenant_id: str | uuid.UUID) -> bool:
        return (await self.get_by_id(tenant_id)) is not None
