from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.video.base import BaseVideoWorker


class SeedanceWorker(BaseVideoWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        from mediaforge.workers.video.veo import VeoWorker

        delegate = VeoWorker(client=self.client, storage_dir=self.storage_dir, model=self.model)
        return await delegate.run(sku, tenant_id, job_id)
