from __future__ import annotations

import asyncio
import base64
import io
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.rag.vector_store import VectorStore
from mediaforge.storage import get_storage
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker


PLATFORM_ASPECT_RATIO: dict[str, str] = {
    "tiktok": "9:16",
    "douyin": "9:16",
    "kuaishou": "9:16",
    "reels": "9:16",
    "shorts": "9:16",
    "xiaohongshu": "3:4",
    "rednote": "3:4",
    "instagram": "1:1",
    "facebook": "1:1",
    "taobao": "1:1",
    "tmall": "1:1",
    "amazon": "1:1",
    "shopee": "1:1",
    "lazada": "1:1",
    "jd": "1:1",
    "pinduoduo": "1:1",
}


def aspect_ratio_for(platform: str) -> str:
    return PLATFORM_ASPECT_RATIO.get(platform.lower(), "1:1")


class BaseImageWorker(ABC):
    """Base for image-generation workers.

    Provides shared helpers for:
      * resolving the SKU's product image URL to a filesystem path,
      * RAG-based reference lookup + LLM style analysis,
      * compliance check + image generation + asset persistence.
    """

    output_type: str = "main_image"

    def __init__(
        self,
        client,
        storage_dir: str,
        model: str,
        vector_store: VectorStore | None = None,
    ):
        self.client = client
        self.storage_dir = storage_dir
        self.model = model
        self.vector_store = vector_store

    @abstractmethod
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        ...

    SCENE_KEYWORDS = (
        "场景", "外景", "户外", "街头", "街景", "街道", "巷子", "巷弄",
        "水乡", "江南", "古镇", "海边", "沙滩", "海滩", "山", "森林", "树林",
        "草原", "田野", "花园", "庭院", "公园", "湖", "河", "桥", "落叶",
        "咖啡馆", "咖啡店", "餐厅", "民宿", "客厅", "卧室", "书房",
        "雪景", "雪地", "樱花", "竹林", "落日", "黄昏", "清晨", "夜景", "霓虹",
        "lifestyle", "outdoor", "scene", "street", "garden", "beach",
        "forest", "cafe", "park",
    )

    _BACKGROUND_PHRASES = (
        "uncluttered background",
        "clean modern background",
        "clean background",
        "studio-grade lighting with soft shadows",
        "studio lighting",
        "blurred surroundings",
        "premium e-commerce look",
        "premium magazine feel",
    )

    @classmethod
    def _is_scene_hint(cls, style_hint: str | None) -> bool:
        if not style_hint:
            return False
        s = style_hint.lower()
        return any(kw.lower() in s for kw in cls.SCENE_KEYWORDS)

    @classmethod
    def _scene_safe(cls, shot_suffix: str) -> str:
        """Remove background-restrictive phrases so the user's scene wins."""
        cleaned = shot_suffix
        for phrase in cls._BACKGROUND_PHRASES:
            cleaned = cleaned.replace(phrase, "")
        # Collapse double commas/spaces left after removal
        while ",," in cleaned:
            cleaned = cleaned.replace(",,", ",")
        while "  " in cleaned:
            cleaned = cleaned.replace("  ", " ")
        return cleaned.strip(" ,")

    # ----- prompt -----

    def _build_prompt(
        self,
        sku: SkuInput,
        platform: str | None,
        references: list | None = None,
        style_prompt: str | None = None,
        shot_suffix: str | None = None,
    ) -> str:
        base = (
            f"High-quality e-commerce product photo of {sku.product_name},"
            f" category {sku.category}"
        )
        if sku.style_hint:
            base += f", style: {sku.style_hint}"
        if platform:
            base += f", optimized for {platform}"
        if shot_suffix:
            effective_suffix = (
                self._scene_safe(shot_suffix)
                if self._is_scene_hint(sku.style_hint)
                else shot_suffix
            )
            if effective_suffix:
                base += f". {effective_suffix}"
        if style_prompt:
            base += f". Visual style reference: {style_prompt}"
        elif references:
            ref_ids = ", ".join([r.product_id for r in references])
            base += f", reference style from products: {ref_ids}"
        return base

    # ----- shared pipeline helpers -----

    def _resolve_product_image_path(self, sku: SkuInput) -> str | None:
        """Map the SKU's product_image_url (e.g. /uploads/<tenant>/<file>) to
        a filesystem path under settings.upload_dir.
        """
        url = sku.product_image_url
        if not url:
            return None
        if not url.startswith("/"):
            return url
        from mediaforge.config import get_settings
        s = get_settings()
        prefix = s.upload_url_prefix.rstrip("/")
        if url.startswith(prefix + "/"):
            rel = url[len(prefix) + 1:]
            return str(Path(s.upload_dir).resolve() / rel)
        return url

    async def _resolve_reference(
        self, sku: SkuInput
    ) -> tuple[str | None, str | None]:
        """Return (ref_image_path, style_prompt).

        Priority:
          1. Explicit ref_sku_id — find it in the vector store by ID, use its image_url.
          2. Auto RAG retrieval — hybrid_search by product_name + category, use top-1 hit.
          3. Fallback — (None, None).
        """
        if not self.vector_store:
            return None, None

        ref_image_url: str | None = None

        if sku.ref_sku_id:
            try:
                results = await self.vector_store.hybrid_search(
                    image_path=None,
                    text=sku.ref_sku_id,
                    category="",
                    top_k=10,
                )
                for r in results:
                    if getattr(r, "product_id", None) == sku.ref_sku_id:
                        ref_image_url = getattr(r, "image_url", None)
                        break
                if not ref_image_url:
                    logger.warning(
                        "ref_sku_id={} not found in vector store, falling back to auto RAG",
                        sku.ref_sku_id,
                    )
            except Exception as exc:
                logger.warning("ref_sku_id lookup failed: {}", exc)

        if not ref_image_url:
            try:
                results = await self.vector_store.hybrid_search(
                    image_path=None,
                    text=sku.product_name,
                    category=sku.category,
                    top_k=5,
                )
                if results:
                    ref_image_url = getattr(results[0], "image_url", None)
                    if ref_image_url:
                        logger.info(
                            "Auto RAG selected ref={} for sku={}",
                            getattr(results[0], "product_id", "?"),
                            sku.sku_id,
                        )
            except Exception as exc:
                logger.warning(
                    "Auto RAG retrieval failed for sku={}: {}", sku.sku_id, exc
                )

        if not ref_image_url:
            return None, None

        ref_path: str | None = None
        p = Path(ref_image_url)
        if p.is_absolute() and p.exists():
            ref_path = str(p)
        elif ref_image_url.startswith("/"):
            ref_path = ref_image_url

        style_prompt: str | None = None
        if ref_path:
            style_prompt = await self._analyze_style(ref_path, sku.product_name)

        return ref_path, style_prompt

    async def _analyze_style(
        self, image_path: str, product_description: str
    ) -> str | None:
        try:
            from mediaforge.config import get_settings
            import httpx
            from PIL import Image as _Image

            settings = get_settings()

            def _encode(path: str) -> str:
                with _Image.open(path) as img:
                    img = img.convert("RGB")
                    w, h = img.size
                    max_px = 512
                    if max(w, h) > max_px:
                        ratio = max_px / max(w, h)
                        img = img.resize(
                            (int(w * ratio), int(h * ratio)), _Image.LANCZOS
                        )
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return base64.b64encode(buf.getvalue()).decode("utf-8")

            b64 = await asyncio.to_thread(_encode, image_path)

            payload = {
                "model": settings.agent_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "You are an e-commerce photography expert. "
                                    "Analyze this reference product image and describe its visual style "
                                    "in 50–80 English words that can be used as a generation prompt. "
                                    "Focus on: shooting environment, lighting, background, composition, "
                                    f"color palette, and mood. The new product is: {product_description}. "
                                    "Output only the style description, no preamble."
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 150,
            }
            proxies = (
                {"http://": settings.http_proxy, "https://": settings.http_proxy}
                if settings.http_proxy
                else None
            )
            async with httpx.AsyncClient(timeout=30.0, proxies=proxies) as client:
                resp = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Style analysis failed for {}: {}", image_path, exc)
            return None

    async def _generate_and_save(
        self,
        *,
        sku: SkuInput,
        tenant_id: str,
        job_id: str,
        platform: str,
        prompt: str,
        aspect_ratio: str,
        product_image_path: str | None,
        ref_image_path: str | None,
        variant: str | None = None,
    ) -> AssetOutput:
        """Run compliance + image gen + storage for one (platform, variant) tuple."""
        checker = ComplianceChecker()
        storage = get_storage()
        compliance = checker.check(sku.model_dump(), prompt)
        if compliance.blocked:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=platform,
                status="failed",
                error="L1 blocked",
            )
        try:
            image_bytes = await self.client.generate_image(
                prompt=compliance.modified_prompt,
                model=self.model,
                size="2K",
                aspect_ratio=aspect_ratio,
                product_image_path=product_image_path,
                ref_image_path=ref_image_path,
            )
            asset_id = str(uuid.uuid4())
            path = await storage.save_asset(
                tenant_id, job_id, asset_id, image_bytes, ext="png"
            )
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=platform if not variant else f"{platform}:{variant}",
                status="success",
                file_path=path,
            )
        except Exception as exc:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=platform if not variant else f"{platform}:{variant}",
                status="failed",
                error=str(exc),
            )
