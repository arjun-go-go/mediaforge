import asyncio
import json

import pytest

from mediaforge.db import AssetStatus
from mediaforge.db.job_store import JobStore
from mediaforge.models.job import BatchSubmitPayload, SkuInput
from mediaforge.storage import OutputStorage
from mediaforge.workers.openrouter_client import IMAGE_MODELS

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_create_job_and_publish(db_engine, redis_client, tmp_path):
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
    await store.start_job(job_id)

    storage = OutputStorage(str(tmp_path))
    fake_bytes = b"\x89PNG\r\n\x1a\n"
    path = await storage.save_asset(TENANT_ID, job_id, "asset-1", fake_bytes, ext="png")

    await store.add_asset(
        job_id=job_id,
        tenant_id=TENANT_ID,
        sku_id="SKU-001",
        output_type="main_image",
        model_used=IMAGE_MODELS["pro"],
        status=AssetStatus.success,
        file_path=path,
        platform="amazon",
    )

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"job:{job_id}")

    status = await store.finalize_job(job_id, success=1, failed=0)
    assert status == "done"

    msg = None
    for _ in range(20):
        msg = await pubsub.get_message(timeout=0.1, ignore_subscribe_messages=True)
        if msg is not None:
            break
        await asyncio.sleep(0.05)
    assert msg is not None
    event = json.loads(msg["data"])
    assert event["event"] == "done"
    assert event["job_id"] == job_id
