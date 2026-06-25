import uuid

from loguru import logger

from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.rag.vector_store import VectorStore
from mediaforge.storage import get_storage
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.image.base import BaseImageWorker


class MainImageWorker(BaseImageWorker):
    def __init__(self, client, storage_dir: str, model: str, vector_store: VectorStore | None = None):
        super().__init__(client, storage_dir, model)
        self.vector_store = vector_store

    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        checker = ComplianceChecker()
        storage = get_storage()
        result = WorkerResult()

        # Resolve reference image and style prompt (shared across all platforms for this SKU)
        ref_image_path, style_prompt = await self._resolve_reference(sku)

        for platform in sku.target_platforms:
            prompt = self._build_prompt(sku, platform, style_prompt=style_prompt)
            compliance = checker.check(sku.model_dump(), prompt)
            if compliance.blocked:
                result.failed.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="failed",
                        error="L1 blocked",
                    )
                )
                continue

            try:
                # product_image_path: the SKU's own product photo (Image 1).
                # The URL is a web path like "/uploads/<tenant>/<file>"; map it
                # to a filesystem path under settings.upload_dir.
                product_image_path = None
                url = sku.product_image_url
                if url.startswith("/"):
                    from mediaforge.config import get_settings as _gs
                    s = _gs()
                    prefix = s.upload_url_prefix.rstrip("/")
                    if url.startswith(prefix + "/"):
                        rel = url[len(prefix) + 1:]
                        from pathlib import Path as _P
                        product_image_path = str(_P(s.upload_dir).resolve() / rel)
                    else:
                        product_image_path = url
                image_bytes = await self.client.generate_image(
                    prompt=compliance.modified_prompt,
                    model=self.model,
                    size="2K",
                    aspect_ratio="1:1",
                    product_image_path=product_image_path,
                    ref_image_path=ref_image_path,
                )
                asset_id = str(uuid.uuid4())
                path = await storage.save_asset(
                    tenant_id, job_id, asset_id, image_bytes, ext="png"
                )
                result.success.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="success",
                        file_path=path,
                    )
                )
            except Exception as exc:
                result.failed.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="failed",
                        error=str(exc),
                    )
                )
        return result

    async def _resolve_reference(self, sku: SkuInput) -> tuple[str | None, str | None]:
        """Return (ref_image_path, style_prompt).

        Priority:
          1. Explicit ref_sku_id — find it in the vector store by ID, use its image_url.
          2. Auto RAG retrieval — hybrid_search by product_name + category, use top-1 hit.
          3. Fallback — (None, None).

        If a reference image is found, also call the LLM style analyzer to get a
        descriptive style_prompt that gets appended to the generation prompt.
        """
        if not self.vector_store:
            return None, None

        ref_image_url: str | None = None

        if sku.ref_sku_id:
            # Option A: user explicitly chose a reference SKU
            try:
                results = await self.vector_store.hybrid_search(
                    image_path=None,
                    text=sku.ref_sku_id,
                    category="",
                    top_k=10,
                )
                # Find the exact product_id match
                for r in results:
                    if getattr(r, "product_id", None) == sku.ref_sku_id:
                        ref_image_url = getattr(r, "image_url", None)
                        break
                if not ref_image_url:
                    logger.warning("ref_sku_id={} not found in vector store, falling back to auto RAG", sku.ref_sku_id)
            except Exception as exc:
                logger.warning("ref_sku_id lookup failed: {}", exc)

        if not ref_image_url:
            # Option B: auto RAG retrieval by text + category
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
                logger.warning("Auto RAG retrieval failed for sku={}: {}", sku.sku_id, exc)

        if not ref_image_url:
            return None, None

        # Resolve local absolute paths directly; skip HTTP URLs for now
        from pathlib import Path
        ref_path: str | None = None
        p = Path(ref_image_url)
        if p.is_absolute() and p.exists():
            ref_path = str(p)
        elif ref_image_url.startswith("/"):
            # Treat as server-relative path
            ref_path = ref_image_url
        # (HTTP URLs could be downloaded here if needed; omitted to keep it sync-safe)

        style_prompt: str | None = None
        if ref_path:
            style_prompt = await self._analyze_style(ref_path, sku.product_name)

        return ref_path, style_prompt

    async def _analyze_style(self, image_path: str, product_description: str) -> str | None:
        """Call the LLM to analyze the visual style of a reference image.
        Returns a short English style prompt, or None on failure.
        """
        try:
            from mediaforge.config import get_settings
            from mediaforge.workers.openrouter_client import OpenRouterClient
            import asyncio, base64, io
            from pathlib import Path

            settings = get_settings()

            # Encode reference image at 512px for style analysis
            def _encode(path: str) -> str:
                from PIL import Image as _Image
                with _Image.open(path) as img:
                    img = img.convert("RGB")
                    w, h = img.size
                    max_px = 512
                    if max(w, h) > max_px:
                        ratio = max_px / max(w, h)
                        img = img.resize((int(w * ratio), int(h * ratio)), _Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return base64.b64encode(buf.getvalue()).decode("utf-8")

            b64 = await asyncio.to_thread(_encode, image_path)

            import httpx
            payload = {
                "model": settings.agent_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"You are an e-commerce photography expert. "
                                    f"Analyze this reference product image and describe its visual style "
                                    f"in 50–80 English words that can be used as a generation prompt. "
                                    f"Focus on: shooting environment, lighting, background, composition, "
                                    f"color palette, and mood. The new product is: {product_description}. "
                                    f"Output only the style description, no preamble."
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 150,
            }
            proxies = {"http://": settings.http_proxy, "https://": settings.http_proxy} if settings.http_proxy else None
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
