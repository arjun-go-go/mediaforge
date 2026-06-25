from typing import Any

from pydantic import BaseModel


class RagItem(BaseModel):
    product_id: str
    category: str
    style: str
    color: str
    material: str
    image_url: str = ""
    text_embedding: list[float] | None = None
    image_embedding: list[float] | None = None
    sparse_embedding: dict[int, float] | None = None


class RagResult(BaseModel):
    product_id: str
    score: float
    image_url: str = ""
    metadata: dict[str, Any]
