import pytest

from mediaforge.models.job import AssetOutput
from mediaforge.orchestrator.nodes import prepare_retry, route_after_generation, validate_job
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


def _failed_asset(error: str) -> AssetOutput:
    return AssetOutput(
        sku_id="SKU-001",
        output_type="main_image",
        model_used="fast",
        platform="amazon",
        status="failed",
        error=error,
    )


def test_quality_failure_routes_to_retry():
    state = {
        "failed": [_failed_asset(
            '生成图质量检查未通过: {"product_consistency":70,"reason":"服装融合不自然"}'
        )],
        "retry_count": 0,
    }
    assert route_after_generation(state) == "prepare_retry"


def test_prepare_retry_selects_staged_mode_for_product_mismatch():
    state = {
        "failed": [_failed_asset(
            '生成图质量检查未通过: {"product_consistency":70,"reason":"主体不一致"}'
        )],
        "retry_count": 0,
        "generation_context": {
            "input_matches": True,
            "retrieval_mode": "none",
        },
    }
    update = prepare_retry(state)
    assert update["generation_mode"] == "staged"
    assert update["active_image_model"] == "pro"
    assert update["retry_count"] == 1


def test_retry_stops_after_one_attempt():
    state = {
        "failed": [_failed_asset(
            '生成图质量检查未通过: {"product_consistency":70}'
        )],
        "retry_count": 1,
    }
    assert route_after_generation(state) == "finalize_job"
