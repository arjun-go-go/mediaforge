from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.video.base import BaseVideoWorker


class VeoWorker(BaseVideoWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        checker = ComplianceChecker()
        result = WorkerResult()

        platform = sku.target_platforms[0] if sku.target_platforms else None
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
                f"{compliance.modified_prompt}\n"
                "First 0-4 seconds: lock exposure and white balance"
            )
            ref_image_path = (
                sku.product_image_url if sku.product_image_url.startswith("/") else None
            )
            video_url = await self.client.generate_video(
                prompt=video_prompt,
                model=self.model,
                duration=5,
                aspect_ratio="9:16",
                ref_image_path=ref_image_path,
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
