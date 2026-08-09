import io

from PIL import Image

from mediaforge.models.job import GenerationContext, SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker


class PinduoduoWhiteBackgroundWorker(BaseImageWorker):
    """Generate the optional 480x480 Pinduoduo white-background catalog asset."""

    output_type = "pdd_white_background"

    @classmethod
    def _resolve_presentation_mode(cls, sku: SkuInput) -> str:
        return "product_only"

    async def run(
        self,
        sku: SkuInput,
        tenant_id: str,
        job_id: str,
        generation_context: GenerationContext | None = None,
        generation_mode: str = "standard",
    ) -> WorkerResult:
        result = WorkerResult()
        if "pinduoduo" not in {platform.lower() for platform in sku.target_platforms}:
            return result
        if generation_context is None:
            generation_context = await self.prepare_generation_context(sku, tenant_id)

        prompt = self._build_prompt(
            sku,
            "pinduoduo",
            shot_suffix=(
                "Front-facing catalog cutout on pure white RGB 255,255,255. Exactly one complete "
                "product, centered and large in frame, with clean natural edges and no cast shadow."
            ),
            product_attributes=generation_context.product_attributes,
        )
        asset = await self._generate_and_save(
            sku=sku,
            tenant_id=tenant_id,
            job_id=job_id,
            platform="pinduoduo",
            prompt=prompt,
            aspect_ratio="1:1",
            product_image_path=generation_context.product_image_path,
            ref_image_path=None,
            generation_context=generation_context,
            generation_mode=generation_mode,
        )
        (result.success if asset.status == "success" else result.failed).append(asset)
        return result

    def _prepare_storage_image(self, image_bytes: bytes) -> bytes:
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            background.alpha_composite(rgba)
            resized = background.convert("RGB").resize((480, 480), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            resized.save(output, format="PNG", optimize=True)
            return output.getvalue()

    def _storage_image_checks(self, image_bytes: bytes) -> dict:
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
        reasons: list[str] = []
        if (width, height) != (480, 480):
            reasons.append(f"导出尺寸应为 480x480，实际为 {width}x{height}")
        if len(image_bytes) >= 3 * 1024 * 1024:
            reasons.append(f"导出文件应小于 3MB，实际为 {len(image_bytes) / 1024 / 1024:.2f}MB")
        return {
            "passed": not reasons,
            "width": width,
            "height": height,
            "bytes": len(image_bytes),
            "reason": "；".join(reasons),
        }
