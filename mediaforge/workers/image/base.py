from abc import ABC, abstractmethod

from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult


class BaseImageWorker(ABC):
    def __init__(self, client, storage_dir: str, model: str):
        self.client = client
        self.storage_dir = storage_dir
        self.model = model

    @abstractmethod
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        ...

    def _build_prompt(
        self,
        sku: SkuInput,
        platform: str | None,
        references: list | None = None,
        style_prompt: str | None = None,
    ) -> str:
        base = (
            f"High-quality e-commerce product photo of {sku.product_name},"
            f" category {sku.category}"
        )
        if sku.style_hint:
            base += f", style: {sku.style_hint}"
        if platform:
            base += f", optimized for {platform}"
        if style_prompt:
            base += f". Visual style reference: {style_prompt}"
        elif references:
            ref_ids = ", ".join([r.product_id for r in references])
            base += f", reference style from products: {ref_ids}"
        return base
