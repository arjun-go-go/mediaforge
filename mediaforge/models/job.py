from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OutputType(StrEnum):
    main_image = "main_image"
    detail_page = "detail_page"
    pdd_white_background = "pdd_white_background"


class ImageModelAlias(StrEnum):
    pro = "pro"
    fast = "fast"
    base = "base"


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
    presentation_mode: Literal["auto", "model_wear", "product_only"] = "auto"
    model_preference: Literal["auto", "female", "male", "no_face"] = "auto"
    market: str = Field(default="US", min_length=2, max_length=3)
    aspect_ratio: Literal[
        "auto", "1:1", "3:4", "4:5", "9:16", "16:9", "4:1", "1:4"
    ] = "auto"
    image_size: Literal["1K", "2K", "4K"] = "2K"
    reference_mode: Literal["auto", "specified", "none"] = "auto"
    ref_sku_id: str | None = Field(default=None, description="参考 SKU ID，指定后优先用该 SKU 的图片作为风格参考，未指定时自动 RAG 检索")

    @model_validator(mode="after")
    def _validate_reference(self):
        if self.reference_mode == "specified" and not self.ref_sku_id:
            raise ValueError("ref_sku_id is required when reference_mode is specified")
        return self

    @field_validator("target_platforms")
    @classmethod
    def _validate_target_platforms(cls, value: list[str]) -> list[str]:
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        platforms = [platform.strip().lower() for platform in value if platform.strip()]
        if not platforms:
            raise ValueError("target_platforms cannot be empty")
        unsupported = sorted(set(platforms) - SUPPORTED_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported target_platforms: {', '.join(unsupported)}")
        return platforms

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


class ReferenceCandidate(BaseModel):
    product_id: str
    image_url: str = ""
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class GenerationContext(BaseModel):
    product_image_path: str | None = None
    input_matches: bool = False
    input_reason: str = ""
    retrieval_mode: Literal["none", "specified", "hybrid"] = "none"
    retrieval_query: str = ""
    retrieval_routes: list[str] = Field(default_factory=list)
    reference_candidates: list[ReferenceCandidate] = Field(default_factory=list)
    selected_reference_id: str | None = None
    ref_image_path: str | None = None
    style_prompt: str | None = None
    presentation_mode: Literal["model_wear", "product_only"] = "product_only"
    model_preference: Literal["auto", "female", "male", "no_face"] = "auto"
    product_attributes: dict = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    quality_results: list[dict] = Field(default_factory=list)
    retry_count: int = 0
    retry_mode: Literal["none", "strict", "staged"] = "none"


class BatchSubmitPayload(BaseModel):
    skus: list[SkuInput] = Field(min_length=1, max_length=5000)
    image_model: ImageModelAlias = ImageModelAlias.pro
    video_model: VideoModelAlias = VideoModelAlias.veo
    priority: Literal["low", "normal", "high"] = "normal"

    @model_validator(mode="after")
    def _unique_sku_ids(self):
        sku_ids = [sku.sku_id for sku in self.skus]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValueError("sku_id must be unique within a batch")
        return self

    @property
    def total_skus(self) -> int:
        return len(self.skus)
