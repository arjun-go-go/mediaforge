"""Refresh token persistence.

Tokens are stored by sha256 hash so that a DB leak does not reveal valid
refresh tokens. The plaintext `jti` is also stored (it is public inside
the JWT and only useful as an index/lookup key).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import RefreshTokenTable

_rt_tbl = RefreshTokenTable.__table__


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class RefreshTokenStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def create(
        self,
        *,
        user_id: str | uuid.UUID,
        jti: str,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> uuid.UUID:
        token_id = uuid.uuid4()
        async with self.engine.connect() as conn:
            await conn.execute(
                _rt_tbl.insert().values(
                    token_id=token_id,
                    user_id=_as_uuid(user_id),
                    jti=jti,
                    token_hash=token_hash,
                    user_agent=user_agent,
                    ip_address=ip_address,
                    expires_at=expires_at,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()
        return token_id

    async def get_by_hash(self, token_hash: str) -> dict | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_rt_tbl).where(_rt_tbl.c.token_hash == token_hash)
            )
            row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_jti(self, jti: str) -> dict | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_rt_tbl).where(_rt_tbl.c.jti == jti)
            )
            row = result.mappings().first()
        return dict(row) if row else None

    async def revoke(self, token_hash: str) -> bool:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                update(_rt_tbl)
                .where(
                    _rt_tbl.c.token_hash == token_hash,
                    _rt_tbl.c.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await conn.commit()
        return result.rowcount > 0

    async def revoke_all_for_user(self, user_id: str | uuid.UUID) -> int:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                update(_rt_tbl)
                .where(
                    _rt_tbl.c.user_id == _as_uuid(user_id),
                    _rt_tbl.c.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await conn.commit()
        return result.rowcount

    async def purge_expired(self) -> int:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                delete(_rt_tbl).where(
                    _rt_tbl.c.expires_at < datetime.now(timezone.utc)
                )
            )
            await conn.commit()
        return result.rowcount
