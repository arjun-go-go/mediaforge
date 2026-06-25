import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config  # noqa: E402

mediaforge.config.clear_settings_cache()

import asyncio  # noqa: E402
from datetime import datetime  # noqa: E402
from uuid import UUID  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fakeredis.aioredis import FakeRedis  # noqa: E402
from fastapi import Depends, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from mediaforge.db.job_store import JobStore  # noqa: E402
from mediaforge.db.tables import Base  # noqa: E402
from mediaforge.gateway.dependencies import (  # noqa: E402
    get_job_store,
    get_tenant_only,
)
from mediaforge.gateway.main import app  # noqa: E402
from mediaforge.models.job import BatchSubmitPayload, SkuInput  # noqa: E402
from mediaforge.models.tenant import Tenant, TenantPlan  # noqa: E402

TENANT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_TENANT_ID = UUID("660e8400-e29b-41d4-a716-446655440001")


def _make_payload() -> BatchSubmitPayload:
    return BatchSubmitPayload(
        skus=[
            SkuInput(
                sku_id="SKU-001",
                product_image_url="https://example.com/img.jpg",
                product_name="Dress",
                category="apparel",
                target_platforms=["amazon"],
                output_types=["main_image"],
                market="US",
            )
        ]
    )


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    redis = FakeRedis(decode_responses=True)
    store = JobStore(engine, redis)
    tenant = Tenant(
        tenant_id=TENANT_ID,
        name="Test Pro",
        api_key_hash="",
        plan=TenantPlan.pro,
    )

    async def override_get_tenant_only(_principal=Depends(lambda: None)):
        return tenant

    async def override_get_job_store():
        return store

    app.dependency_overrides[get_tenant_only] = override_get_tenant_only
    app.dependency_overrides[get_job_store] = override_get_job_store

    test_client = TestClient(app)
    test_client.store = store
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        await redis.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_tasks_requires_auth():
    """No dependency overrides -> real auth gate kicks in and returns 401."""
    response = TestClient(app).get("/api/v1/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_tasks_returns_jobs_for_tenant(client):
    store = client.store
    payload = _make_payload()
    auth_job_ids = []
    for _ in range(3):
        job_id = await store.create_job(tenant_id=str(TENANT_ID), payload=payload)
        auth_job_ids.append(job_id)
        await asyncio.sleep(0.01)

    for _ in range(2):
        await store.create_job(tenant_id=str(OTHER_TENANT_ID), payload=payload)

    response = client.get("/api/v1/tasks", headers={"X-Api-Key": "demo-key-pro"})
    assert response.status_code == 200
    data = response.json()
    jobs = data["jobs"]
    assert isinstance(jobs, list)
    assert len(jobs) == 3
    assert {job["job_id"] for job in jobs} == set(auth_job_ids)

    timestamps = [datetime.fromisoformat(job["created_at"]) for job in jobs]
    assert all(timestamps[i] >= timestamps[i + 1] for i in range(len(timestamps) - 1))

    for job in jobs:
        assert job["status"] == "pending"
        assert job["total_skus"] == 1
        assert job["done_skus"] == 0
        assert datetime.fromisoformat(job["created_at"])


@pytest.mark.asyncio
async def test_list_tasks_limit_is_respected(client):
    store = client.store
    payload = _make_payload()
    for _ in range(3):
        await store.create_job(tenant_id=str(TENANT_ID), payload=payload)
        await asyncio.sleep(0.01)

    response = client.get(
        "/api/v1/tasks?limit=2", headers={"X-Api-Key": "demo-key-pro"}
    )
    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 2


@pytest.mark.asyncio
async def test_list_tasks_limit_above_max_returns_422(client):
    response = client.get(
        "/api/v1/tasks?limit=101", headers={"X-Api-Key": "demo-key-pro"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks_invalid_tenant_id_returns_400(client):
    class _BadStore:
        async def list_jobs_for_tenant(self, *a, **kw):
            raise ValueError("bad tenant id")

    invalid_tenant = Tenant(
        tenant_id=UUID("00000000-0000-0000-0000-000000000099"),
        name="Bad Tenant",
        api_key_hash="",
        plan=TenantPlan.pro,
    )

    async def override_invalid_tenant(_principal=Depends(lambda: None)):
        return invalid_tenant

    app.dependency_overrides[get_tenant_only] = override_invalid_tenant
    app.dependency_overrides[get_job_store] = lambda: _BadStore()
    try:
        response = client.get("/api/v1/tasks", headers={"X-Api-Key": "demo-key-pro"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid tenant ID"
    finally:
        app.dependency_overrides.clear()
