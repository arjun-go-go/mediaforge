from langgraph.graph import END, START, StateGraph

from mediaforge.orchestrator.nodes import (
    fan_out,
    finalize_job,
    image_worker,
    validate_job,
    video_worker,
)
from mediaforge.orchestrator.state import JobState


async def build_batch_graph():
    builder = StateGraph(JobState)
    builder.add_node("validate_job", validate_job)
    builder.add_node("image_worker", image_worker)
    builder.add_node("video_worker", video_worker)
    builder.add_node("finalize_job", finalize_job)

    builder.add_edge(START, "validate_job")
    builder.add_conditional_edges("validate_job", fan_out, ["image_worker", "video_worker"])
    builder.add_edge("image_worker", "finalize_job")
    builder.add_edge("video_worker", "finalize_job")
    builder.add_edge("finalize_job", END)

    return builder.compile()
