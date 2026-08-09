from mediaforge.models.job import GenerationContext, SkuInput
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

    async def run(
        self,
        sku: SkuInput,
        tenant_id: str,
        job_id: str,
        generation_context: GenerationContext | None = None,
        generation_mode: str = "standard",
    ) -> WorkerResult:
        result = WorkerResult()
        if generation_context is None:
            generation_context = await self.prepare_generation_context(sku, tenant_id)
        ref_image_path = generation_context.ref_image_path
        style_prompt = generation_context.style_prompt
        product_image_path = generation_context.product_image_path

        for platform in sku.target_platforms:
            prompt = self._build_prompt(
                sku,
                platform,
                style_prompt=style_prompt,
                shot_suffix=self.SHOT_SUFFIX,
                product_attributes=generation_context.product_attributes,
            )
            asset = await self._generate_and_save(
                sku=sku,
                tenant_id=tenant_id,
                job_id=job_id,
                platform=platform,
                prompt=prompt,
                aspect_ratio=(
                    aspect_ratio_for(platform)
                    if sku.aspect_ratio == "auto"
                    else sku.aspect_ratio
                ),
                product_image_path=product_image_path,
                ref_image_path=ref_image_path,
                generation_context=generation_context,
                generation_mode=generation_mode,
            )
            if asset.status == "success":
                result.success.append(asset)
            else:
                result.failed.append(asset)
        return result
