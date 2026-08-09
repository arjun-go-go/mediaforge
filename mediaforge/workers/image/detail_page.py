from mediaforge.models.job import GenerationContext, SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker, aspect_ratio_for


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
            "Lifestyle scene shot, visibly different from the main catalog image: show the product in a "
            "credible furnished environment with at least two readable contextual elements, not a plain "
            "seamless studio wall. For model-wear apparel, use a natural three-quarter or full-body walking, "
            "turning or interacting pose from a different camera angle while keeping the garment readable. "
            "Use soft natural light, depth and an aspirational mood",
        ),
        (
            "feature",
            "Selling-point feature shot, not a generic catalog portrait. Use a shoulder-to-hip or similarly "
            "tight editorial crop so the product occupies most of the frame. Emphasize one source-supported "
            "benefit such as fit, silhouette, drape or construction through the model pose and camera angle. "
            "For a top, a natural hand gesture may reveal the hem, width or drape without stretching or "
            "redesigning it. Keep clean negative space for later marketing copy but generate no text, labels "
            "or invented callouts",
        ),
        (
            "closeup",
            "Macro close-up detail shot: crop tightly into one detail visibly supported by the source image, "
            "such as neckline, stitching, texture or construction. Use sharp focus and soft side light; "
            "do not invent fabric texture, labels or components that cannot be verified",
        ),
    ]

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
            generated_paths: list[tuple[str, str]] = []
            for variant, shot_suffix in self.SHOTS:
                prompt = self._build_prompt(
                    sku,
                    platform,
                    style_prompt=style_prompt,
                    shot_suffix=shot_suffix,
                    product_attributes=generation_context.product_attributes,
                )
                asset = await self._generate_and_save(
                    sku=sku,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    platform=platform,
                    prompt=prompt,
                    aspect_ratio=(
                        aspect_ratio_for(platform, self.output_type)
                        if sku.aspect_ratio == "auto"
                        else sku.aspect_ratio
                    ),
                    product_image_path=product_image_path,
                    ref_image_path=ref_image_path,
                    variant=variant,
                    generation_context=generation_context,
                    generation_mode=generation_mode,
                )
                if asset.status == "success":
                    result.success.append(asset)
                    if asset.file_path:
                        generated_paths.append((variant, asset.file_path))
                else:
                    result.failed.append(asset)
            if len(generated_paths) == len(self.SHOTS) and product_image_path:
                detail_set_audit = await self._validate_detail_set(
                    product_image_path, generated_paths
                )
                generation_context.quality_results.append(
                    {
                        "asset": f"{platform}:detail_set",
                        "output_type": self.output_type,
                        "model": self.client.model_name(self.model),
                        **detail_set_audit,
                    }
                )
        return result
