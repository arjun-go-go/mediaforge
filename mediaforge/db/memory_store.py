from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from mediaforge.db.tables import MemoryTable


class MemoryStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def get(self, tenant_id: str, key: str) -> str | None:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(MemoryTable.__table__.c.value)
                .where(MemoryTable.__table__.c.tenant_id == tenant_id)
                .where(MemoryTable.__table__.c.key == key)
            )
            row = result.mappings().first()
            return row["value"] if row else None

    async def set(self, tenant_id: str, key: str, value: str) -> None:
        async with self.engine.connect() as conn:
            existing = await conn.execute(
                select(MemoryTable.__table__.c.memory_id)
                .where(MemoryTable.__table__.c.tenant_id == tenant_id)
                .where(MemoryTable.__table__.c.key == key)
            )
            row = existing.mappings().first()
            if row:
                await conn.execute(
                    update(MemoryTable.__table__)
                    .where(MemoryTable.__table__.c.memory_id == row["memory_id"])
                    .values(value=value)
                )
            else:
                await conn.execute(
                    MemoryTable.__table__.insert().values(
                        tenant_id=tenant_id, key=key, value=value
                    )
                )
            await conn.commit()
