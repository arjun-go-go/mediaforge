import uuid

from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.video.base import BaseVideoWorker


class VeoWorker(BaseVideoWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        checker = ComplianceChecker()
        result = WorkerResult()

        platform = sku.target_platforms[0] if sku.target_platforms else None
        from mediaforge.db import AssetStatus, get_engine, get_redis
        from mediaforge.db.job_store import JobStore

        store = JobStore(get_engine(), await get_redis())
        existing = await store.get_asset(job_id, sku.sku_id, "video", platform)
        if existing and existing["status"] == AssetStatus.success:
            result.success.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=existing["model_used"],
                    platform=platform,
                    status="success",
                    file_path=existing["file_path"],
                )
            )
            return result

        prompt = self._build_prompt(sku, platform)
        compliance = checker.check(sku.model_dump(), prompt)

        if compliance.blocked:
            result.failed.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="failed",
                    error="L1 blocked",
                )
            )
            return result

        try:
            video_prompt = (
                f"{compliance.modified_prompt}\nFirst 0-4 seconds: lock exposure and white balance"
            )
            ref_image_path = sku.product_image_url or None
            video_url = await self.client.generate_video(
                prompt=video_prompt,
                model=self.model,
                duration=5,
                aspect_ratio="9:16",
                ref_image_path=ref_image_path,
            )
            import httpx

            from mediaforge.storage import get_storage

            async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
                response = await client.get(video_url, follow_redirects=True)
            response.raise_for_status()
            asset_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"mediaforge:{job_id}:{sku.sku_id}:video:{platform or ''}",
                )
            )
            video_url = await get_storage().save_asset(
                tenant_id, job_id, asset_id, response.content, ext="mp4"
            )
            await store.add_asset(
                job_id=job_id,
                tenant_id=tenant_id,
                sku_id=sku.sku_id,
                output_type="video",
                model_used=self.client.model_name(self.model),
                status=AssetStatus.success,
                file_path=video_url,
                platform=platform,
            )
            result.success.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="success",
                    file_path=video_url,
                )
            )
        except Exception as exc:
            result.failed.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="failed",
                    error=str(exc),
                )
            )
        return result
