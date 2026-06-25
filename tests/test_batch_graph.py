from unittest.mock import patch

import pytest

from mediaforge.models.job import AssetOutput
from mediaforge.workers.base import WorkerResult

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
JOB_ID = "660e8400-e29b-41d4-a716-446655440000"


def _set_required_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "secret-test")


@pytest.mark.asyncio
async def test_batch_graph_runs_to_done(db_engine, redis_client, tmp_path, monkeypatch):
    from mediaforge.orchestrator.batch_graph import build_batch_graph
    from mediaforge.orchestrator.state import JobState, SkuInput

    _set_required_env(monkeypatch)

    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image"],
        market="US",
    )
    initial = JobState(
        job_id=JOB_ID,
        tenant_id=TENANT_ID,
        skus=[sku],
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
        result = await graph.ainvoke(initial, {"configurable": {"thread_id": "thread-t1"}})

    assert result["status"] == "done"
    assert len(result["completed"]) == 1
