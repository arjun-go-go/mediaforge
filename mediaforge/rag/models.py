from typing import Any

from pydantic import BaseModel


class RagItem(BaseModel):
    document_id: str
    product_id: str
    tenant_id: str = ""
    visibility: str = "global"
    source_type: str = "local_seed"
    category: str
    style: str
    color: str
    material: str
    season: str = ""
    sales_count: int = 0
    price: float | None = None
    platform: str = ""
    market: str = ""
    quality_status: str = "approved"
    image_url: str = ""
    search_text: str = ""
    text_embedding: list[float] | None = None
    image_embedding: list[float] | None = None


class RagResult(BaseModel):
    product_id: str
    score: float
    image_url: str = ""
    metadata: dict[str, Any]
