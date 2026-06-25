import uuid

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mediaforge.db.engine import close_engine, get_engine, get_session  # noqa: F401
from mediaforge.db.tables import Base, JobStatus, JobTable, TenantTable


@pytest.fixture(autouse=True)
async def _reset_engine():
    yield
    await close_engine()


@pytest.mark.asyncio
async def test_create_tables(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = get_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result.all()}
    assert "tenants" in tables
    assert "jobs" in tables
    assert "assets" in tables
    assert JobStatus.pending.value == "pending"


@pytest.mark.asyncio
async def test_job_status_default(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = get_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()
    async with AsyncSession(engine) as session:
        await session.execute(
            insert(TenantTable).values(
                tenant_id=tenant_id, name="Test", api_key_hash="hash", plan="starter"
            )
        )
        await session.execute(
            insert(JobTable).values(job_id=job_id, tenant_id=tenant_id, total_skus=1, input_data={})
        )
        await session.commit()

    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(JobTable.__table__).where(JobTable.__table__.c.job_id == job_id)
        )
        row = result.mappings().one()
        assert row["status"] == JobStatus.pending
