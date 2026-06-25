from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OutputType(StrEnum):
    main_image = "main_image"
    detail_page = "detail_page"
    video = "video"
    social = "social"


class ImageModelAlias(StrEnum):
    pro = "pro"
    fast = "fast"


class VideoModelAlias(StrEnum):
    veo = "veo"
    seedance = "seedance"


class SkuInput(BaseModel):
    sku_id: str = Field(min_length=1)
    product_image_url: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    target_platforms: list[str] = Field(default_factory=list)
    output_types: list[str]
    style_hint: str | None = None
    market: str = Field(default="US", min_length=2, max_length=3)
    ref_sku_id: str | None = Field(default=None, description="参考 SKU ID，指定后优先用该 SKU 的图片作为风格参考，未指定时自动 RAG 检索")

    @field_validator("output_types")
    @classmethod
    def _validate_output_types(cls, v: list[str]) -> list[str]:
        allowed = {m.value for m in OutputType}
        for item in v:
            if item not in allowed:
                raise ValueError(f"Invalid output_type: {item}")
        if not v:
            raise ValueError("output_types cannot be empty")
        return v


class AssetOutput(BaseModel):
    sku_id: str
    output_type: str
    file_path: str | None = None
    model_used: str
    platform: str | None = None
    status: Literal["success", "failed", "retrying"]
    error: str | None = None


class BatchSubmitPayload(BaseModel):
    skus: list[SkuInput] = Field(min_length=1, max_length=5000)
    image_model: ImageModelAlias = ImageModelAlias.pro
    video_model: VideoModelAlias = VideoModelAlias.veo
    priority: Literal["low", "normal", "high"] = "normal"

    @property
    def total_skus(self) -> int:
        return len(self.skus)
