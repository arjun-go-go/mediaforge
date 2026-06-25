from unittest.mock import patch

import pytest

from mediaforge.db.job_store import JobStore
from mediaforge.models.job import AssetOutput, BatchSubmitPayload, SkuInput
from mediaforge.orchestrator.batch_graph import build_batch_graph
from mediaforge.orchestrator.state import JobState
from mediaforge.workers.base import WorkerResult

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "secret-test")


@pytest.mark.asyncio
async def test_batch_graph_persists_assets(db_engine, redis_client, tmp_path, monkeypatch):
    _set_required_env(monkeypatch)

    # Ensure get_settings reads the patched env values when the graph runs.
    from mediaforge.config import clear_settings_cache

    clear_settings_cache()

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

    initial = JobState(
        job_id=job_id,
        tenant_id=TENANT_ID,
        skus=payload.skus,
        total_sku_count=1,
        status="running",
    )

    graph = build_batch_graph(engine=db_engine)
    with (
        patch("mediaforge.orchestrator.nodes.get_engine", return_value=db_engine),
        patch("mediaforge.orchestrator.nodes.get_redis", return_value=redis_client),
        patch("mediaforge.workers.image.main_image.MainImageWorker.run") as mock_run,
    ):
        mock_run.return_value = WorkerResult(
            success=[
                AssetOutput(
                    sku_id="SKU-001",
                    output_type="main_image",
                    model_used="google/gemini-3-pro-image",
                    platform="amazon",
                    status="success",
                    file_path=str(tmp_path / "img.png"),
                )
            ]
        )
        await graph.ainvoke(initial, {"configurable": {"thread_id": "thread-t1"}})

    assets = await store.get_assets_for_job(job_id)
    assert len(assets) == 1
    assert assets[0]["status"] == "success"
