import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from mediaforge.auth.tenant import TenantResolver
from mediaforge.db.tables import Base
from mediaforge.models.tenant import Tenant, TenantPlan
from mediaforge.models.user import User


os.environ.setdefault("JWT_SECRET", "mediaforge-test-secret-at-least-32-bytes")
os.environ.setdefault("JWT_REFRESH_SECRET", "mediaforge-test-refresh-secret-32-bytes")


@pytest.fixture(autouse=True)
def test_api_key_resolver(monkeypatch):
    """Use explicit test-only API keys without restoring production demo keys."""

    async def resolve_by_api_key(self, api_key: str):
        plans = {
            "test-api-key-starter": TenantPlan.starter,
            "test-api-key-pro": TenantPlan.pro,
        }
        plan = plans.get(api_key)
        if plan is None:
            raise ValueError("Invalid API key")
        tenant_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        return (
            User(
                user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                tenant_id=tenant_id,
                email="test@mediaforge.local",
            ),
            Tenant(tenant_id=tenant_id, name="Test workspace", plan=plan),
        )

    monkeypatch.setattr(TenantResolver, "resolve_by_api_key", resolve_by_api_key)


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
