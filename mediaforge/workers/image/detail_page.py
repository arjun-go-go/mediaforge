from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker


class DetailPageWorker(BaseImageWorker):
    """Generate a set of product-detail-page images per platform.

    Detail pages typically combine three visual roles:
      * `scene` — lifestyle/contextual shot showing the product in use,
      * `feature` — annotated feature highlight emphasizing selling points,
      * `closeup` — macro detail shot showing material/craftsmanship.

    All variants render in 3:4 portrait, which is the dominant aspect ratio
    for marketplace and content-platform detail pages.
    """

    output_type = "detail_page"

    SHOTS: list[tuple[str, str]] = [
        (
            "scene",
            "Lifestyle scene shot: the product naturally in use within a real environment "
            "that matches the target audience, soft natural lighting, depth of field, "
            "warm and aspirational mood, model or hands optional but secondary to product",
        ),
        (
            "feature",
            "Selling-point feature shot: product centered with clean modern background, "
            "leave generous negative space on the right side for marketing copy, "
            "balanced product geometry, even soft lighting, premium magazine feel",
        ),
        (
            "closeup",
            "Macro close-up detail shot: zoom into one signature material, stitching, "
            "texture or component of the product, razor-sharp focus, dramatic side "
            "lighting that reveals texture, blurred surroundings",
        ),
    ]

    DETAIL_ASPECT_RATIO = "3:4"

    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        result = WorkerResult()
        ref_image_path, style_prompt = await self._resolve_reference(sku)
        product_image_path = self._resolve_product_image_path(sku)

        for platform in sku.target_platforms:
            for variant, shot_suffix in self.SHOTS:
                prompt = self._build_prompt(
                    sku,
                    platform,
                    style_prompt=style_prompt,
                    shot_suffix=shot_suffix,
                )
                asset = await self._generate_and_save(
                    sku=sku,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    platform=platform,
                    prompt=prompt,
                    aspect_ratio=self.DETAIL_ASPECT_RATIO,
                    product_image_path=product_image_path,
                    ref_image_path=ref_image_path,
                    variant=variant,
                )
                if asset.status == "success":
                    result.success.append(asset)
                else:
                    result.failed.append(asset)
        return result
