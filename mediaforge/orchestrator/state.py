import operator
from typing import Annotated, Literal

from typing_extensions import TypedDict

from mediaforge.models.job import AssetOutput, SkuInput


def _add_asset_outputs(
    current: list[AssetOutput], update: list[AssetOutput]
) -> list[AssetOutput]:
    return current + update


class JobState(TypedDict):
    job_id: str
    tenant_id: str
    skus: list[SkuInput]
    completed: Annotated[list[AssetOutput], _add_asset_outputs]
    failed: Annotated[list[AssetOutput], _add_asset_outputs]
    logs: Annotated[list[str], operator.add]
    total_sku_count: int
    status: Literal["running", "done", "partial_fail", "failed"]
