import asyncio
import json

import pytest

from mediaforge.db import AssetStatus, JobStatus
from mediaforge.db.job_store import JobStore
from mediaforge.models.job import BatchSubmitPayload, SkuInput

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_create_job_and_assets(db_engine, redis_client):
    store = JobStore(db_engine, redis_client)
    payload = BatchSubmitPayload(
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
    job_id = await store.create_job(tenant_id=TENANT_ID, payload=payload)
    assert job_id

    job = await store.get_job(job_id)
    assert job["status"] == "pending"

    await store.add_asset(
        job_id=job_id,
        tenant_id=TENANT_ID,
        sku_id="SKU-001",
        output_type="main_image",
        model_used="google/gemini-3-pro-image",
        status=AssetStatus.success,
        file_path="/outputs/t-1/job/sku_main.png",
    )
    assets = await store.get_assets_for_job(job_id)
    assert len(assets) == 1
    assert assets[0]["status"] == "success"

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"job:{job_id}")

    await store.finalize_job(job_id, success=1, failed=0)
    job = await store.get_job(job_id)
    assert job["status"] == "done"

    message = None
    for _ in range(20):
        message = await pubsub.get_message(timeout=0.1, ignore_subscribe_messages=True)
        if message is not None:
            break
        await asyncio.sleep(0.05)
    assert message is not None
    payload = json.loads(message["data"])
    assert payload["event"] == "done"
    assert payload["job_id"] == job_id


@pytest.mark.asyncio
async def test_start_job(db_engine, redis_client):
    store = JobStore(db_engine, redis_client)
    payload = BatchSubmitPayload(
        skus=[
            SkuInput(
                sku_id="SKU-002",
                product_image_url="https://example.com/img.jpg",
                product_name="Shirt",
                category="apparel",
                target_platforms=["amazon"],
                output_types=["main_image"],
                market="US",
            )
        ]
    )
    job_id = await store.create_job(tenant_id=TENANT_ID, payload=payload)
    await store.start_job(job_id)
    job = await store.get_job(job_id)
    assert job["status"] == JobStatus.running


@pytest.mark.asyncio
async def test_partial_fail_status(db_engine, redis_client):
    store = JobStore(db_engine, redis_client)
    payload = BatchSubmitPayload(
        skus=[
            SkuInput(
                sku_id="SKU-003",
                product_image_url="https://example.com/img.jpg",
                product_name="Pants",
                category="apparel",
                target_platforms=["amazon"],
                output_types=["main_image"],
                market="US",
            )
        ]
    )
    job_id = await store.create_job(tenant_id=TENANT_ID, payload=payload)
    await store.finalize_job(job_id, success=1, failed=1)
    job = await store.get_job(job_id)
    assert job["status"] == JobStatus.partial_fail
