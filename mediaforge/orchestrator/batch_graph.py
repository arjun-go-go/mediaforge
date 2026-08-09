from langgraph.graph import END, START, StateGraph

from mediaforge.orchestrator.nodes import (
    finalize_job,
    image_worker,
    prepare_generation_context,
    prepare_retry,
    route_after_generation,
    validate_job,
)
from mediaforge.orchestrator.state import JobState


async def build_batch_graph():
    builder = StateGraph(JobState)
    builder.add_node("validate_job", validate_job)
    builder.add_node("prepare_generation_context", prepare_generation_context)
    builder.add_node("image_worker", image_worker)
    builder.add_node("prepare_retry", prepare_retry)
    builder.add_node("finalize_job", finalize_job)

    builder.add_edge(START, "validate_job")
    builder.add_edge("validate_job", "prepare_generation_context")
    builder.add_edge("prepare_generation_context", "image_worker")
    builder.add_conditional_edges(
        "image_worker",
        route_after_generation,
        ["prepare_retry", "finalize_job"],
    )
    builder.add_edge("prepare_retry", "image_worker")
    builder.add_edge("finalize_job", END)

    return builder.compile()
