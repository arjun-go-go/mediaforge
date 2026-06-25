from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker


class SocialWorker(BaseImageWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        return WorkerResult()
