"""API key persistence layer.

Keys are stored as sha256(plaintext) so a DB leak cannot be used to
authenticate. The prefix (first 12 chars like "mf_aB3xY9...")
is stored in plaintext for display purposes only.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import ApiKeyTable

_tbl = ApiKeyTable.__table__


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (plaintext_key, key_prefix, key_hash) where:
    - plaintext_key   — shown to user ONCE; never stored
    - key_prefix      — "mf_<first 8 random chars>" shown in listings
    - key_hash        — sha256(plaintext_key) stored in DB
    """
    raw = secrets.token_urlsafe(32)
    plaintext = f"mf_{raw}"
    prefix = plaintext[:12]
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, prefix, key_hash


class ApiKeyStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def create(
        self,
        *,
        tenant_id: str | uuid.UUID,
        created_by: str | uuid.UUID | None,
        name: str,
        key_prefix: str,
        key_hash: str,
        expires_at: datetime | None = None,
    ) -> dict:
        key_id = uuid.uuid4()
        async with self.engine.connect() as conn:
            await conn.execute(
                _tbl.insert().values(
                    key_id=key_id,
                    tenant_id=_as_uuid(tenant_id),
                    created_by=_as_uuid(created_by) if created_by else None,
                    name=name,
                    key_prefix=key_prefix,
                    key_hash=key_hash,
                    expires_at=expires_at,
                    created_at=_now(),
                )
            )
            await conn.commit()
        return await self.get_by_id(key_id)

    async def get_by_id(self, key_id: str | uuid.UUID) -> dict | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(
                select(_tbl).where(_tbl.c.key_id == _as_uuid(key_id))
            )).mappings().first()
        return dict(row) if row else None

    async def get_by_hash(self, key_hash: str) -> dict | None:
        async with self.engine.connect() as conn:
            row = (await conn.execute(
                select(_tbl).where(
                    _tbl.c.key_hash == key_hash,
                    _tbl.c.revoked_at.is_(None),
                )
            )).mappings().first()
        return dict(row) if row else None

    async def list_for_tenant(self, tenant_id: str | uuid.UUID) -> list[dict]:
        async with self.engine.connect() as conn:
            rows = (await conn.execute(
                select(_tbl)
                .where(_tbl.c.tenant_id == _as_uuid(tenant_id))
                .order_by(_tbl.c.created_at.desc())
            )).mappings().all()
        return [dict(r) for r in rows]

    async def revoke(self, key_id: str | uuid.UUID, tenant_id: str | uuid.UUID) -> bool:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                update(_tbl)
                .where(
                    _tbl.c.key_id == _as_uuid(key_id),
                    _tbl.c.tenant_id == _as_uuid(tenant_id),
                    _tbl.c.revoked_at.is_(None),
                )
                .values(revoked_at=_now())
            )
            await conn.commit()
        return result.rowcount > 0

    async def touch_last_used(self, key_id: str | uuid.UUID) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                update(_tbl)
                .where(_tbl.c.key_id == _as_uuid(key_id))
                .values(last_used_at=_now())
            )
            await conn.commit()
