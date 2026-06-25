from mediaforge.orchestrator.state import JobState


def test_job_state_reducer_accumulates():
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[],
        total_sku_count=0,
        status="running",
    )
    update1 = {
        "completed": [
            {
                "sku_id": "SKU-001",
                "output_type": "main_image",
                "model_used": "pro",
                "status": "success",
            }
        ]
    }
    update2 = {
        "completed": [
            {
                "sku_id": "SKU-002",
                "output_type": "main_image",
                "model_used": "pro",
                "status": "success",
            }
        ]
    }
    from mediaforge.orchestrator.state import _add_asset_outputs

    merged = _add_asset_outputs(state.get("completed", []), update1["completed"])
    merged = _add_asset_outputs(merged, update2["completed"])
    assert len(merged) == 2
