import operator

from mediaforge.orchestrator.state import JobState


def test_job_state_logs_reducer_accumulates():
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[],
        total_sku_count=0,
        status="running",
    )
    merged = operator.add(state.get("logs", []), ["prepared"])
    merged = operator.add(merged, ["generated"])
    assert len(merged) == 2
    assert merged == ["prepared", "generated"]
