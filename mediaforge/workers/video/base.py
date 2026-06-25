from abc import ABC, abstractmethod

from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult


class BaseVideoWorker(ABC):
    def __init__(self, client, storage_dir: str, model: str):
        self.client = client
        self.storage_dir = storage_dir
        self.model = model

    @abstractmethod
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        ...

    def _build_prompt(self, sku: SkuInput, platform: str | None) -> str:
        base = f"Engaging short video for {sku.product_name}, category {sku.category}"
        if sku.style_hint:
            base += f", style: {sku.style_hint}"
        if platform:
            base += f", optimized for {platform}"
        return base
