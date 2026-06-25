"""User persistence helpers.

All password-related work (hashing, verification) lives in
`mediaforge.auth.password`. This module only deals with rows.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import UserTable
from mediaforge.models.user import User

_user_tbl = UserTable.__table__


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _row_to_user(row) -> User:
    return User(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        email=row["email"],
        display_name=row["display_name"],
        email_verified_at=row["email_verified_at"],
        status=row["status"],
        created_at=row["created_at"],
    )


class UserStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def get_by_email(self, email: str) -> dict | None:
        """Return the raw row mapping (includes password_hash) for auth flows."""
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_user_tbl).where(_user_tbl.c.email == email.lower())
            )
            row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(_user_tbl).where(_user_tbl.c.user_id == _as_uuid(user_id))
            )
            row = result.mappings().first()
        if row is None:
            return None
        return _row_to_user(row)

    async def create(
        self,
        *,
        tenant_id: str | uuid.UUID,
        email: str,
        password_hash: str,
        display_name: str | None = None,
    ) -> User:
        uid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        async with self.engine.connect() as conn:
            await conn.execute(
                _user_tbl.insert().values(
                    user_id=uid,
                    tenant_id=_as_uuid(tenant_id),
                    email=email.lower(),
                    password_hash=password_hash,
                    display_name=display_name,
                    status="active",
                    failed_login_attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            await conn.commit()
        return User(
            user_id=uid,
            tenant_id=_as_uuid(tenant_id),
            email=email.lower(),
            display_name=display_name,
            status="active",
            created_at=now,
        )

    async def record_login_failure(self, user_id: str | uuid.UUID, *, lock_until: datetime | None) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                update(_user_tbl)
                .where(_user_tbl.c.user_id == _as_uuid(user_id))
                .values(
                    failed_login_attempts=_user_tbl.c.failed_login_attempts + 1,
                    locked_until=lock_until,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()

    async def record_login_success(self, user_id: str | uuid.UUID) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                update(_user_tbl)
                .where(_user_tbl.c.user_id == _as_uuid(user_id))
                .values(
                    failed_login_attempts=0,
                    locked_until=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()

    async def mark_email_verified(self, user_id: str | uuid.UUID) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                update(_user_tbl)
                .where(_user_tbl.c.user_id == _as_uuid(user_id))
                .values(
                    email_verified_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await conn.commit()
