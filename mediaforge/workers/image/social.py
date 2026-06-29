from mediaforge.models.job import SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image.base import BaseImageWorker, aspect_ratio_for


SOCIAL_PLATFORMS = {
    "tiktok", "douyin", "kuaishou", "reels", "shorts",
    "xiaohongshu", "rednote",
    "instagram", "facebook",
}


class SocialWorker(BaseImageWorker):
    """Generate social-feed creatives tuned per platform.

    A social ad image needs higher stopping power than a marketplace hero:
    bold composition, strong color contrast, expressive lifestyle moment.
    Aspect ratio follows platform conventions (9:16 short-video, 3:4 Xiaohongshu,
    1:1 Instagram feed). Marketplace-only platforms (taobao, amazon...) are
    skipped — social creatives don't apply there.
    """

    output_type = "social"

    PLATFORM_SUFFIX: dict[str, str] = {
        "tiktok": (
            "Vertical short-video poster style, high-energy lifestyle moment, "
            "saturated colors, dynamic composition with diagonal lines, "
            "scroll-stopping visual hook, captures attention within 1 second"
        ),
        "douyin": (
            "抖音信息流封面风格, 强视觉冲击, 高饱和度配色, 主体居中偏上为字幕留白, "
            "生活化场景, 真实质感, 适合竖屏快速滑动"
        ),
        "kuaishou": (
            "快手信息流风格, 接地气的生活场景, 暖色调, 真实感强, "
            "突出产品在日常使用中的价值"
        ),
        "reels": (
            "Instagram Reels vertical creative, trendy aesthetic, soft pastel "
            "or bold neon palette, lifestyle moment, fashion-forward composition"
        ),
        "shorts": (
            "YouTube Shorts thumbnail style, bold contrast, clear focal point, "
            "expressive moment, optimized for mobile vertical viewing"
        ),
        "xiaohongshu": (
            "小红书种草笔记封面风格, 3:4 竖版, 莫兰迪或日系清新配色, "
            "精致生活场景, 文艺质感, 高级感构图, 适合 KOL 笔记封面"
        ),
        "rednote": (
            "Xiaohongshu (RedNote) lifestyle note cover, soft Morandi or "
            "Japanese-inspired palette, curated cozy moment, refined composition"
        ),
        "instagram": (
            "Instagram square feed creative, magazine-quality lifestyle shot, "
            "balanced composition, on-trend color grading, lifestyle storytelling"
        ),
        "facebook": (
            "Facebook feed ad creative, clear product focal point, "
            "lifestyle context, balanced composition, broad appeal"
        ),
    }

    DEFAULT_SUFFIX = (
        "Social feed creative, lifestyle-oriented composition, "
        "scroll-stopping visual hook, strong color presence"
    )

    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        result = WorkerResult()
        ref_image_path, style_prompt = await self._resolve_reference(sku)
        product_image_path = self._resolve_product_image_path(sku)

        for platform in sku.target_platforms:
            if platform.lower() not in SOCIAL_PLATFORMS:
                continue
            shot_suffix = self.PLATFORM_SUFFIX.get(platform.lower(), self.DEFAULT_SUFFIX)
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
                aspect_ratio=aspect_ratio_for(platform),
                product_image_path=product_image_path,
                ref_image_path=ref_image_path,
            )
            if asset.status == "success":
                result.success.append(asset)
            else:
                result.failed.append(asset)
        return result
