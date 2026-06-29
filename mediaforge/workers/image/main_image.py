from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker, aspect_ratio_for


class MainImageWorker(BaseImageWorker):
    """Generate the primary product hero shot for each target platform.

    Goal: a clean, conversion-oriented product image — well-lit, sharp,
    minimal distraction. Aspect ratio adapts to the target platform
    (1:1 marketplaces, 9:16 short-video feeds, 3:4 Xiaohongshu).
    """

    output_type = "main_image"

    SHOT_SUFFIX = (
        "Hero product shot, full product clearly visible and centered, "
        "studio-grade lighting with soft shadows, crisp focus on the product, "
        "uncluttered background, premium e-commerce look"
    )

    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        result = WorkerResult()
        ref_image_path, style_prompt = await self._resolve_reference(sku)
        product_image_path = self._resolve_product_image_path(sku)

        for platform in sku.target_platforms:
            prompt = self._build_prompt(
                sku,
                platform,
                style_prompt=style_prompt,
                shot_suffix=self.SHOT_SUFFIX,
            )
            asset = await self._generate_and_save(
                sku=sku,
                tenant_id=tenant_id,
                job_id=job_id,
                platform=platform,
                prompt=prompt,
                aspect_ratio=aspect_ratio_for(platform),
                product_image_path=product_image_path,
                ref_image_path=ref_image_path,
            )
            if asset.status == "success":
                result.success.append(asset)
            else:
                result.failed.append(asset)
        return result
