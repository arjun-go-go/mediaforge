import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from mediaforge.db.tables import Base


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client():
    from fakeredis.aioredis import FakeRedis

    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
