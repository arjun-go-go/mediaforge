import operator
from typing import Annotated, Literal

from typing_extensions import TypedDict

from mediaforge.models.job import AssetOutput, SkuInput


class JobState(TypedDict):
    job_id: str
    tenant_id: str
    skus: list[SkuInput]
    completed: list[AssetOutput]
    failed: list[AssetOutput]
    logs: Annotated[list[str], operator.add]
    total_sku_count: int
    image_model: str
    active_image_model: str
    video_model: str
    generation_context: dict
    generation_mode: Literal["standard", "strict", "staged"]
    retry_count: int
    status: Literal["running", "done", "partial_fail", "failed"]
