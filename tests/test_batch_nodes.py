import pytest

from mediaforge.orchestrator.nodes import fan_out, validate_job
from mediaforge.orchestrator.state import JobState, SkuInput


def test_validate_job_rejects_empty_skus():
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[],
        total_sku_count=0,
        status="running",
    )
    with pytest.raises(ValueError):
        validate_job(state)


def test_fan_out_creates_image_and_video_sends():
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image", "video"],
        market="US",
    )
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[sku],
        total_sku_count=1,
        status="running",
    )
    sends = fan_out(state)
    assert len(sends) == 2
    assert {s.node for s in sends} == {"image_worker", "video_worker"}
