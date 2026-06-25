"""Audit log persistence — fire-and-forget writes.

Call `audit()` from auth and job routers. Failures are swallowed so they
never disrupt the primary request path.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import AuditLogTable

_tbl = AuditLogTable.__table__


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def log(
        self,
        *,
        action: str,
        success: bool = True,
        tenant_id: Any = None,
        user_id: Any = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        def _to_uuid(v: Any) -> uuid.UUID | None:
            if v is None:
                return None
            return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))

        try:
            async with self.engine.connect() as conn:
                await conn.execute(
                    _tbl.insert().values(
                        log_id=uuid.uuid4(),
                        tenant_id=_to_uuid(tenant_id),
                        user_id=_to_uuid(user_id),
                        action=action,
                        success=1 if success else 0,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        metadata_=metadata,
                        created_at=_now(),
                    )
                )
                await conn.commit()
        except Exception as exc:
            logger.warning("Audit log write failed (non-fatal): action={} err={}", action, exc)


async def audit(
    action: str,
    *,
    success: bool = True,
    tenant_id: Any = None,
    user_id: Any = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Convenience wrapper — creates a short-lived engine connection."""
    from mediaforge.db.engine import get_engine
    store = AuditStore(get_engine())
    await store.log(
        action=action,
        success=success,
        tenant_id=tenant_id,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
