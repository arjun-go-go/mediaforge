from __future__ import annotations

import asyncio
import json
import re
import uuid
from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel, Field

from mediaforge.models.job import (
    AssetOutput,
    GenerationContext,
    ReferenceCandidate,
    SkuInput,
)
from mediaforge.rag.vector_store import VectorStore
from mediaforge.storage import get_storage
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.platform_rules import (
    aspect_ratio_for as aspect_ratio_for,
)
from mediaforge.workers.platform_rules import (
    audit_instruction,
    get_platform_rule,
)


class ProductInputAudit(BaseModel):
    matches: bool
    observed_product: str
    reason: str


class GeneratedImageAudit(BaseModel):
    passed: bool
    product_consistency: int = Field(ge=0, le=100)
    garment_fusion: int = Field(ge=0, le=100)
    visual_quality: int = Field(ge=0, le=100)
    platform_compliance: int = Field(ge=0, le=100)
    model_preference_match: int = Field(ge=0, le=100)
    intent_adherence: int = Field(ge=0, le=100)
    issues: list[str]
    reason: str


class FocusedProductAudit(BaseModel):
    same_product: bool
    product_consistency: int = Field(ge=0, le=100)
    reason: str


class GarmentStructureAudit(BaseModel):
    item_count: int = Field(ge=1)
    garment_types: list[str]
    colors: list[str]
    material: str
    pattern: str
    neckline: str
    sleeve_length: str
    closures: list[str]
    pockets: str
    waistband: str
    garment_length: str
    silhouette: str
    logos_or_embroidery: str
    distinctive_details: list[str]


class DetailSetAudit(BaseModel):
    passed: bool
    distinctiveness: int = Field(ge=0, le=100)
    role_coverage: int = Field(ge=0, le=100)
    issues: list[str]
    reason: str


class BaseImageWorker(ABC):
    """Base for image-generation workers.

    Provides shared helpers for:
      * resolving the SKU's product image location,
      * RAG-based reference lookup + LLM style analysis,
      * compliance check + image generation + asset persistence.
    """

    output_type: str = "main_image"

    def __init__(
        self,
        client,
        model: str,
        vector_store: VectorStore | None = None,
    ):
        self.client = client
        self.model = model
        self.vector_store = vector_store
        self._input_validation_cache: dict[str, tuple[bool, str, str]] = {}

    @abstractmethod
    async def run(
        self,
        sku: SkuInput,
        tenant_id: str,
        job_id: str,
        generation_context: GenerationContext | None = None,
        generation_mode: str = "standard",
    ) -> WorkerResult: ...

    SCENE_KEYWORDS = (
        "场景",
        "外景",
        "户外",
        "街头",
        "街景",
        "街道",
        "巷子",
        "巷弄",
        "水乡",
        "江南",
        "古镇",
        "海边",
        "沙滩",
        "海滩",
        "山",
        "森林",
        "树林",
        "草原",
        "田野",
        "花园",
        "庭院",
        "公园",
        "湖",
        "河",
        "桥",
        "落叶",
        "咖啡馆",
        "咖啡店",
        "餐厅",
        "民宿",
        "客厅",
        "卧室",
        "书房",
        "雪景",
        "雪地",
        "樱花",
        "竹林",
        "落日",
        "黄昏",
        "清晨",
        "夜景",
        "霓虹",
        "lifestyle",
        "outdoor",
        "scene",
        "street",
        "garden",
        "beach",
        "forest",
        "cafe",
        "park",
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

    _APPAREL_TERMS = (
        "服饰", "服装", "女装", "男装", "童装", "上衣", "衬衫", "t恤",
        "毛衣", "针织", "开衫", "卫衣", "夹克", "外套", "风衣", "大衣",
        "连衣裙", "半身裙", "裤", "牛仔", "短裤", "套装", "西装", "礼服",
        "apparel", "clothing", "garment", "dress", "shirt", "t-shirt", "tshirt", "tee",
        "top", "blouse", "sweater", "cardigan", "hoodie", "jacket", "coat",
        "jeans", "pants", "trousers", "skirt", "shorts", "suit", "leggings",
    )

    _CATEGORY_FAMILIES = {
        "top": ("t恤", "上衣", "衬衫", "针织", "毛衣", "背心", "tee", "shirt", "top", "blouse", "sweater", "cardigan", "tank"),
        "bottom": ("裤", "牛仔裤", "半身裙", "短裤", "pants", "trousers", "jeans", "skirt", "shorts", "culottes", "leggings"),
        "dress": ("连衣裙", "礼服", "dress", "gown"),
        "outerwear": ("夹克", "外套", "风衣", "大衣", "jacket", "coat", "hoodie", "blazer"),
    }

    @classmethod
    def _category_family(cls, text: str) -> str | None:
        normalized = text.lower().replace("_", " ").replace("-", " ")
        for family, terms in cls._CATEGORY_FAMILIES.items():
            if any(term.lower() in normalized for term in terms):
                return family
        return None

    @classmethod
    def _resolve_presentation_mode(cls, sku: SkuInput) -> str:
        if sku.presentation_mode != "auto":
            return sku.presentation_mode
        if sku.model_preference in {"female", "male", "no_face"}:
            return "model_wear"
        product_text = f"{sku.category} {sku.product_name}".lower()
        return (
            "model_wear"
            if any(term.lower() in product_text for term in cls._APPAREL_TERMS)
            else "product_only"
        )

    def _presentation_prompt(self, sku: SkuInput) -> str:
        if self._resolve_presentation_mode(sku) == "product_only":
            return (
                "Present the product itself as the sole visual subject. Do not add a model or "
                "make a person wear, hold or obscure it unless a requested detail shot needs a "
                "minimal supporting hand."
            )
        model_subject = {
            "female": "a female model",
            "male": "a male model",
            "no_face": "a suitable model whose face is turned away or naturally hidden",
        }.get(sku.model_preference, "a suitable model")
        framing = (
            "Show the model head-to-toe and keep every sellable garment fully visible. "
            if self.output_type == "main_image"
            else "Use the requested detail-page framing while keeping the garment naturally worn. "
        )
        return (
            f"Create a photorealistic promotional photograph of {model_subject} naturally wearing every "
            "clothing item shown in the SOURCE PRODUCT IMAGE. "
            + framing
            + (
                "The model's face must not be visible, while the complete garment remains visible. "
                if sku.model_preference == "no_face"
                else ""
            )
            + "Preserve the exact garment count, category, neckline, sleeves, buttons, waistband, "
            "length, silhouette, fabric, color, pattern and construction details. Remove the "
            "flat-lay background, hanger, packaging and unrelated tags. Do not paste the flat "
            "garment onto the body. The garment must fit naturally with realistic folds, draping, "
            "fabric tension, body contact and occlusion."
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
        product_attributes: dict | None = None,
    ) -> str:
        strict_catalog_image = (
            self.output_type == "main_image"
            and bool(platform)
            and platform.lower() == "amazon"
        ) or self.output_type == "pdd_white_background"
        base = (
            f"Create a high-quality e-commerce photo of the exact product shown in the "
            f"SOURCE PRODUCT IMAGE. The declared product is {sku.product_name}, category "
            f"{sku.category}. The source image is authoritative when text and image conflict. "
            "Do not change the product category, silhouette, construction, color, material, "
            "pattern, proportions or distinctive details. Do not replace it with the product "
            "from any style reference."
        )
        base += f". {self._presentation_prompt(sku)}"
        if product_attributes:
            facts = json.dumps(product_attributes, ensure_ascii=False, separators=(",", ":"))
            base += (
                ". STRUCTURED GARMENT FACTS FROM THE SOURCE IMAGE (hard constraints): "
                f"{facts}. Preserve every visible listed item and attribute exactly; do not add, "
                "remove, merge or redesign any garment piece"
            )
        ignore_style_hint = self.output_type == "pdd_white_background" or (
            strict_catalog_image and self._is_scene_hint(sku.style_hint)
        )
        if sku.style_hint and not ignore_style_hint:
            base += (
                f". USER SCENE AND STYLE DIRECTION: {sku.style_hint}. Follow this explicit user "
                "direction wherever it does not conflict with product identity or platform rules"
            )
        if platform:
            base += f", optimized for {platform}"
        if shot_suffix:
            effective_suffix = (
                self._scene_safe(shot_suffix)
                if self._is_scene_hint(sku.style_hint) and not strict_catalog_image
                else shot_suffix
            )
            if effective_suffix:
                base += f". {effective_suffix}"
        if style_prompt:
            base += (
                ". Use the bestseller analysis only to fill visual details not explicitly set by "
                f"the user or platform: {style_prompt}. Keep the source product unchanged."
            )
        elif references:
            ref_ids = ", ".join([r.product_id for r in references])
            base += f", reference style from products: {ref_ids}"
        return base

    @staticmethod
    def _parse_json_object(raw: str) -> dict:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise ValueError(f"Vision audit returned invalid JSON: {raw[:200]}")
            return json.loads(match.group(0))

    async def _vision_audit(
        self,
        images: list[tuple[str, str | bytes]],
        instruction: str,
        schema: type[BaseModel],
    ) -> dict:
        from mediaforge.config import get_settings
        from mediaforge.workers.openrouter_client import OpenRouterClient

        content: list[dict] = []
        for label, source in images:
            content.append({"type": "text", "text": label})
            encoded = await OpenRouterClient._encode_image(source, max_px=768)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                }
            )
        content.append({"type": "text", "text": instruction})
        parsed = await self.client.structured_chat_completion(
            messages=[{"role": "user", "content": content}],
            schema=schema,
            model=get_settings().quality_model,
            max_tokens=800,
        )
        return parsed.model_dump()

    async def _validate_product_input(
        self, sku: SkuInput, product_image_path: str | None
    ) -> tuple[bool, str, str]:
        cached = self._input_validation_cache.get(sku.sku_id)
        if cached is not None:
            return cached
        if not product_image_path:
            result = (False, "缺少商品原图", "")
            self._input_validation_cache[sku.sku_id] = result
            return result
        generic_category = sku.category.strip().lower() in {
            "",
            "general",
            "unknown",
            "其他",
        }
        automatic_name = (
            sku.product_name.strip() == "用户上传商品"
            or re.fullmatch(
                r"(?:clipboard|pasted|upload(?:ed)?(?:[-_]?product)?|image|img)[-_]?(?:\d+|[0-9a-f-]{8,})?",
                sku.product_name.strip(),
                re.IGNORECASE,
            )
            is not None
            or re.fullmatch(
                r"sku[-_ ]?[a-z0-9]+(?:[-_][a-z0-9]+)*",
                sku.product_name.strip(),
                re.IGNORECASE,
            )
            is not None
        )
        generic_upload = generic_category and automatic_name
        instruction = (
            "No semantic product name or category was supplied. The declared name is only an "
            "automatic upload label and must not be compared with the visual product. Check only "
            "that the image contains a clear sellable product or coordinated product set suitable "
            "for e-commerce. Return matches=true when the product is clearly visible, and identify "
            "the actual product category and visible garment pieces in "
            "observed_product. Return JSON only: {\"matches\": true|false, "
            "\"observed_product\": \"...\", \"reason\": \"concise Chinese explanation\"}."
            if generic_upload
            else (
                "Check whether the dominant sellable product in the image matches the declared "
                f"product name '{sku.product_name}' and category '{sku.category}'. Distinguish "
                "tops, T-shirts, dresses, skirts, pants, shoes and accessories carefully. "
                "Return JSON only: {\"matches\": true|false, \"observed_product\": \"...\", "
                "\"reason\": \"concise Chinese explanation\"}."
            )
        )
        audit = await self._vision_audit(
            [("SOURCE PRODUCT IMAGE", product_image_path)],
            instruction,
            ProductInputAudit,
        )
        matches = bool(audit.get("matches"))
        observed_product = str(audit.get("observed_product") or "")
        reason = str(audit.get("reason") or audit.get("observed_product") or "商品信息不一致")
        result = (matches, reason, observed_product)
        self._input_validation_cache[sku.sku_id] = result
        return result

    async def _validate_generated_image(
        self,
        *,
        sku: SkuInput,
        platform: str,
        aspect_ratio: str,
        image_size: str,
        product_image_path: str,
        ref_image_path: str | None,
        generated_image: bytes,
        product_attributes: dict | None = None,
        variant: str | None = None,
    ) -> dict:
        deterministic = await asyncio.to_thread(
            self._check_image_properties,
            generated_image,
            aspect_ratio,
            image_size,
            (
                self.output_type == "pdd_white_background"
                or (
                    self.output_type == "main_image"
                    and get_platform_rule(platform).require_white_border
                )
            ),
            self.client.model_name(self.model),
        )
        images: list[tuple[str, str | bytes]] = [
            ("SOURCE PRODUCT IMAGE", product_image_path),
        ]
        if ref_image_path:
            images.append(("STYLE REFERENCE IMAGE", ref_image_path))
        images.append(("GENERATED IMAGE", generated_image))
        platform_audit = audit_instruction(platform, self.output_type)
        presentation_mode = self._resolve_presentation_mode(sku)
        intent_instruction = {
            "scene": (
                "This is the lifestyle-scene role. Show the product in a credible real environment; "
                "for model_wear apparel it must be naturally worn. A plain isolated catalog product fails this role."
            ),
            "feature": (
                "This is the selling-point role. Use a deliberate feature-focused composition with "
                "an emphasized benefit or construction area and usable negative space. A generic catalog image fails this role."
            ),
            "closeup": (
                "This is the close-up role. Show a genuine macro crop of a visible source-supported "
                "material or construction detail. A full-product image or invented detail fails this role."
            ),
        }.get(
            variant,
            "This is the main-image role. Clearly and completely present the product in the platform-appropriate hero composition.",
        )
        preference_instruction = (
            f"The requested model preference is '{sku.model_preference}'. Score model_preference_match "
            "0-100 by checking the visible model presentation; for no_face, the face must not be "
            "visible while the garment remains complete. "
            if presentation_mode == "model_wear" and sku.model_preference != "auto"
            else "Set model_preference_match to 100. "
        )
        attributes_instruction = (
            "Treat these source-image garment facts as exact audit criteria, including piece count, "
            f"types and construction details: {json.dumps(product_attributes, ensure_ascii=False)}. "
            if product_attributes
            else ""
        )
        garment_fusion_instruction = (
            "Because this is model_wear apparel imagery, also score garment_fusion 0-100. Check "
            "neckline, shoulders, sleeves, waist, hems, natural folds, drape, fabric tension, body "
            "contact and occlusion; reject pasted-on clothing, body/garment intersections, leftover "
            "flat-lay backgrounds, hangers, packaging, unrelated tags, missing set pieces, or copied "
            "reference garments. "
            if presentation_mode == "model_wear"
            else "Set garment_fusion to 100 because this is product_only imagery. "
        )
        audit = await self._vision_audit(
            images,
            (
                "Audit the GENERATED IMAGE as an e-commerce asset. The generated product must be "
                "the same product as the SOURCE PRODUCT IMAGE; the style reference may influence "
                "only composition, lighting, background and mood. Score 0-100 for "
                "product_consistency, visual_quality and platform_compliance. "
                f"Output type is '{self.output_type}', platform is '{platform}', requested aspect "
                f"ratio is '{aspect_ratio}', presentation mode is '{presentation_mode}'. "
                f"Score intent_adherence 0-100 against this required visual role: {intent_instruction} "
                + garment_fusion_instruction
                + preference_instruction
                + attributes_instruction
                + f"Platform-specific audit criteria: {platform_audit} "
                + "Return JSON only: {\"passed\": true|false, \"product_consistency\": 0, "
                "\"garment_fusion\": 0, \"visual_quality\": 0, \"platform_compliance\": 0, "
                "\"model_preference_match\": 0, \"intent_adherence\": 0, "
                "\"issues\": [], \"reason\": \"concise Chinese explanation\"}."
            ),
            GeneratedImageAudit,
        )
        product_score = int(audit.get("product_consistency", 0))
        garment_fusion_score = int(audit.get("garment_fusion", 0))
        visual_score = int(audit.get("visual_quality", 0))
        platform_score = int(audit.get("platform_compliance", 0))
        preference_score = int(
            audit.get(
                "model_preference_match",
                100 if presentation_mode != "model_wear" or sku.model_preference == "auto" else 0,
            )
        )
        intent_score = int(audit.get("intent_adherence", 0))
        if 80 <= product_score < 85:
            focused_review = await self._vision_audit(
                [
                    ("SOURCE PRODUCT IMAGE", product_image_path),
                    ("GENERATED IMAGE", generated_image),
                ],
                (
                    "Independently recheck only whether the GENERATED IMAGE preserves the same "
                    "sellable product as the SOURCE PRODUCT IMAGE. Ignore background, lighting, "
                    "model identity, pose and normal shape changes caused by wearing a garment. "
                    "Compare garment count, type, color, pattern, neckline, sleeves, construction "
                    "and distinctive details. "
                    + attributes_instruction
                    + "Return JSON only: {\"same_product\": true|false, "
                    "\"product_consistency\": 0, \"reason\": \"concise Chinese explanation\"}."
                ),
                FocusedProductAudit,
            )
            review_score = int(focused_review.get("product_consistency", 0))
            audit["product_consistency_initial"] = product_score
            audit["product_consistency_review"] = review_score
            audit["product_consistency_review_reason"] = str(
                focused_review.get("reason") or ""
            )
            if focused_review.get("same_product") and review_score >= 85:
                product_score = review_score
                audit["product_consistency"] = review_score
        audit["model_passed"] = bool(audit.get("passed"))
        audit["deterministic_checks"] = deterministic
        audit["passed"] = (
            product_score >= 85 and visual_score >= 70 and platform_score >= 70
            and (presentation_mode != "model_wear" or garment_fusion_score >= 80)
            and (sku.model_preference == "auto" or preference_score >= 80)
            and intent_score >= 75
            and deterministic["passed"]
        )
        if not deterministic["passed"]:
            audit["reason"] = "；".join(
                filter(None, [str(audit.get("reason") or ""), deterministic["reason"]])
            )
        failed_checks: list[str] = []
        if product_score < 85:
            failed_checks.append(f"商品一致性 {product_score}<85")
        if visual_score < 70:
            failed_checks.append(f"视觉质量 {visual_score}<70")
        if platform_score < 70:
            failed_checks.append(f"平台合规性 {platform_score}<70")
        if presentation_mode == "model_wear" and garment_fusion_score < 80:
            failed_checks.append(f"服装融合质量 {garment_fusion_score}<80")
        if sku.model_preference != "auto" and preference_score < 80:
            failed_checks.append(f"模特偏好匹配 {preference_score}<80")
        if intent_score < 75:
            failed_checks.append(f"输出意图实现度 {intent_score}<75")
        if not deterministic["passed"]:
            failed_checks.append(str(deterministic["reason"]))
        audit["failed_checks"] = failed_checks
        audit["passed"] = not failed_checks
        if failed_checks:
            audit["audit_reason"] = str(audit.get("reason") or "")
            audit["reason"] = "未通过指标：" + "；".join(failed_checks)
        return audit

    @staticmethod
    def _check_image_properties(
        image_bytes: bytes,
        aspect_ratio: str,
        image_size: str,
        require_white_border: bool,
        model_name: str = "",
    ) -> dict:
        import io

        from PIL import Image

        # GPT Image 2 exposes quality tiers rather than 1K/2K/4K resolution tiers.
        # Its concrete pixel dimensions are selected by the provider and aspect ratio.
        expected_min = (
            768
            if model_name == "openai/gpt-image-2"
            else {"1K": 768, "2K": 1536, "4K": 3000}.get(image_size, 768)
        )
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            width, height = image.size
            reasons: list[str] = []
            if max(width, height) < expected_min:
                reasons.append(
                    f"分辨率不足：实际 {width}×{height}，{image_size} 至少需要长边 {expected_min}px"
                )

            if ":" in aspect_ratio:
                left, right = aspect_ratio.split(":", 1)
                expected = float(left) / float(right)
                actual = width / height
                if abs(actual - expected) / expected > 0.06:
                    reasons.append(
                        f"图片比例不符：要求 {aspect_ratio}，实际约 {actual:.2f}:1"
                    )

            white_border_ratio = None
            if require_white_border:
                sample = image.copy()
                sample.thumbnail((256, 256))
                sw, sh = sample.size
                band = max(1, int(min(sw, sh) * 0.08))
                border_pixels = []
                for y in range(sh):
                    for x in range(sw):
                        if x < band or x >= sw - band or y < band or y >= sh - band:
                            border_pixels.append(sample.getpixel((x, y)))
                white = sum(1 for r, g, b in border_pixels if r >= 250 and g >= 250 and b >= 250)
                white_border_ratio = white / max(1, len(border_pixels))
                if white_border_ratio < 0.90:
                    reasons.append(
                        f"图片边缘不是纯白背景：近白像素占比 {white_border_ratio:.1%}"
                    )

        return {
            "passed": not reasons,
            "width": width,
            "height": height,
            "requested_size": image_size,
            "requested_aspect_ratio": aspect_ratio,
            "white_border_ratio": white_border_ratio,
            "reason": "；".join(reasons),
        }

    # ----- shared pipeline helpers -----

    def _resolve_product_image_path(self, sku: SkuInput) -> str | None:
        """Return the product image location (MinIO URL or explicit local path)."""
        url = sku.product_image_url
        return url or None

    async def prepare_generation_context(
        self, sku: SkuInput, tenant_id: str
    ) -> GenerationContext:
        """Prepare reusable SKU context once before any output worker runs."""
        from mediaforge.config import get_settings
        from mediaforge.rag.cached_retriever import CachedRetriever
        from mediaforge.rag.embeddings import DashScopeEmbeddingClient
        from mediaforge.rag.retriever import ReferenceRetriever

        product_image_path = self._resolve_product_image_path(sku)
        matches, reason, observed_product = await self._validate_product_input(
            sku, product_image_path
        )
        if (
            matches
            and sku.presentation_mode == "auto"
            and self._resolve_presentation_mode(sku) == "product_only"
            and self._category_family(observed_product) is not None
        ):
            sku.presentation_mode = "model_wear"
        context = GenerationContext(
            product_image_path=product_image_path,
            input_matches=matches,
            input_reason=reason,
            presentation_mode=self._resolve_presentation_mode(sku),
            model_preference=sku.model_preference,
            retrieval_query=" ".join(
                filter(
                    None,
                    [
                        observed_product or sku.product_name,
                        "" if sku.category.strip().lower() in {"", "general", "unknown", "其他"} else sku.category,
                        sku.style_hint or "",
                    ],
                )
            ),
        )
        if matches and context.presentation_mode == "model_wear" and product_image_path:
            context.product_attributes = await self._analyze_garment_structure(
                sku, product_image_path
            )
        if not matches or sku.reference_mode == "none" or not self.vector_store:
            return context

        candidates = []
        if sku.reference_mode == "specified" and sku.ref_sku_id:
            try:
                selected = await self.vector_store.get_by_product_id(
                    sku.ref_sku_id, tenant_id=tenant_id
                )
                if selected:
                    candidates = [selected]
                    context.retrieval_mode = "specified"
                    context.retrieval_routes = ["scalar_product_id"]
            except Exception as exc:
                logger.warning("Specified reference lookup failed for {}: {}", sku.sku_id, exc)

        if not candidates:
            settings = get_settings()
            embed_client = DashScopeEmbeddingClient()
            query_dense = None
            query_image = None
            routes = ["bm25", "scalar_filter"]
            try:
                async def _text_embedding():
                    try:
                        return await embed_client.embed_text(context.retrieval_query)
                    except Exception as exc:
                        logger.warning("Text embedding failed for {}: {}", sku.sku_id, exc)
                        return None

                async def _image_embedding():
                    if not product_image_path:
                        return None
                    try:
                        return await embed_client.embed_image(product_image_path)
                    except Exception as exc:
                        logger.warning("Image embedding failed for {}: {}", sku.sku_id, exc)
                        return None

                query_dense, query_image = await asyncio.gather(
                    _text_embedding(), _image_embedding()
                )
                if query_dense is not None:
                    routes.append("text_dense")
                if query_image is not None:
                    routes.append("image_dense")

                from mediaforge.db import get_redis

                retriever = ReferenceRetriever(
                    CachedRetriever(self.vector_store, redis=await get_redis())
                )
                candidates = await retriever.retrieve(
                    image_path=product_image_path,
                    text=context.retrieval_query,
                    category=sku.category,
                    tenant_id=tenant_id,
                    top_k=settings.bestseller_candidate_count,
                    query_dense=query_dense,
                    query_image=query_image,
                    min_sales_count=settings.bestseller_min_sales_count,
                    quality_status="approved",
                )

                product_family = self._category_family(
                    f"{sku.category} {sku.product_name} {observed_product}"
                )
                if product_family:
                    candidates = [
                        item
                        for item in candidates
                        if self._category_family(str(item.metadata.get("category") or ""))
                        == product_family
                    ]
                    routes.append(f"category_family:{product_family}")

                if len(candidates) > 1:
                    rerank_input = [
                        {
                            **item.metadata,
                            "product_id": item.product_id,
                            "image_url": item.image_url,
                            "score": item.score,
                            "text": item.metadata.get("text", ""),
                        }
                        for item in candidates
                    ]
                    reranked = await embed_client.rerank(
                        query_text=context.retrieval_query,
                        query_image_path=product_image_path,
                        candidates=rerank_input,
                        top_n=settings.bestseller_style_reference_count,
                    )
                    by_id = {item.product_id: item for item in candidates}
                    candidates = [
                        by_id[item["product_id"]].model_copy(
                            update={"score": item.get("rerank_score", item.get("score", 0.0))}
                        )
                        for item in reranked
                        if item.get("product_id") in by_id
                    ]
                    if any("rerank_score" in item for item in reranked):
                        routes.append("vl_rerank")
                context.retrieval_mode = "hybrid"
                context.retrieval_routes = routes
            except Exception as exc:
                logger.warning("Hybrid reference preparation failed for {}: {}", sku.sku_id, exc)
            finally:
                await embed_client.aclose()

        settings = get_settings()
        candidates = candidates[: settings.bestseller_style_reference_count]
        context.reference_candidates = [
            ReferenceCandidate(
                product_id=item.product_id,
                image_url=item.image_url,
                score=item.score,
                metadata=item.metadata,
            )
            for item in candidates
            if item.image_url
        ]
        if not context.reference_candidates:
            return context

        selected = context.reference_candidates[0]
        context.selected_reference_id = selected.product_id
        context.ref_image_path = selected.image_url
        context.style_prompt = await self._analyze_styles(
            [item.image_url for item in context.reference_candidates],
            sku.product_name,
        )
        return context

    async def _analyze_garment_structure(
        self, sku: SkuInput, product_image_path: str
    ) -> dict:
        """Extract source-image garment facts once for prompts, QA and task details."""
        try:
            audit = await self._vision_audit(
                [("SOURCE PRODUCT IMAGE", product_image_path)],
                (
                    "Extract only clearly visible garment facts from the source product image. "
                    f"Declared product: '{sku.product_name}', category: '{sku.category}'. Do not "
                    "infer hidden details. Return JSON only with this exact shape: "
                    '{"item_count":1,"garment_types":[],"colors":[],"material":"",'
                    '"pattern":"","neckline":"","sleeve_length":"","closures":[],'
                    '"pockets":"","waistband":"","garment_length":"","silhouette":"",'
                    '"logos_or_embroidery":"","distinctive_details":[]}.'
                ),
                GarmentStructureAudit,
            )
            return {
                "item_count": int(audit.get("item_count") or 1),
                "garment_types": audit.get("garment_types") or [],
                "colors": audit.get("colors") or [],
                "material": str(audit.get("material") or ""),
                "pattern": str(audit.get("pattern") or ""),
                "neckline": str(audit.get("neckline") or ""),
                "sleeve_length": str(audit.get("sleeve_length") or ""),
                "closures": audit.get("closures") or [],
                "pockets": str(audit.get("pockets") or ""),
                "waistband": str(audit.get("waistband") or ""),
                "garment_length": str(audit.get("garment_length") or ""),
                "silhouette": str(audit.get("silhouette") or ""),
                "logos_or_embroidery": str(audit.get("logos_or_embroidery") or ""),
                "distinctive_details": audit.get("distinctive_details") or [],
            }
        except Exception as exc:
            logger.warning("Garment structure analysis failed for {}: {}", sku.sku_id, exc)
            return {}

    @staticmethod
    def _style_prompt_is_complete(prompt: str | None) -> bool:
        if not prompt:
            return False
        cleaned = prompt.strip().strip('"')
        words = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", cleaned)
        trailing_incomplete = re.search(
            r"\b(?:a|an|the|of|to|for|with|and|or|in|on|at|from|as)\s*[.!?]?$",
            cleaned,
            flags=re.IGNORECASE,
        )
        return len(words) >= 20 and trailing_incomplete is None and cleaned[-1] in ".!?"

    async def _analyze_styles(
        self, image_paths: list[str], product_description: str
    ) -> str | None:
        try:
            from mediaforge.config import get_settings
            from mediaforge.workers.openrouter_client import OpenRouterClient

            settings = get_settings()
            content: list[dict] = []
            for index, image_path in enumerate(image_paths, start=1):
                b64 = await OpenRouterClient._encode_image(image_path, max_px=512)
                content.append({"type": "text", "text": f"BESTSELLER REFERENCE {index}"})
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    }
                )
            content.append(
                {
                    "type": "text",
                    "text": (
                        "You are an e-commerce photography expert. Analyze the COMMON visual "
                        "style shared by these bestselling references. Ignore their product identity, "
                        "logos, watermarks and embedded text. Describe only reusable scene, lighting, "
                        "background, camera angle, composition, color palette, model pose and mood. "
                        f"The new product is: {product_description}. Write one concise 60-100 word "
                        "English generation prompt. Output only the prompt."
                    ),
                }
            )
            messages = [{"role": "user", "content": content}]
            try:
                style_prompt = await self.client.chat_completion(
                    messages=messages,
                    model=settings.agent_model,
                    max_tokens=600,
                    temperature=0.2,
                )
                if self._style_prompt_is_complete(style_prompt):
                    return style_prompt.strip().strip('"')
                logger.warning("Agent model returned an incomplete style prompt")
            except ValueError:
                logger.warning(
                    "Agent model returned no final style prompt; falling back to quality model"
                )
            style_prompt = await self.client.chat_completion(
                messages=messages,
                model=settings.quality_model,
                max_tokens=220,
                temperature=0.2,
            )
            if self._style_prompt_is_complete(style_prompt):
                return style_prompt.strip().strip('"')
            logger.warning("Quality model also returned an incomplete style prompt")
            return None
        except Exception as exc:
            logger.warning("Style analysis failed for {} references: {}", len(image_paths), exc)
            return None

    async def _validate_detail_set(
        self, product_image_path: str, generated_paths: list[tuple[str, str]]
    ) -> dict:
        images: list[tuple[str, str | bytes]] = [("SOURCE PRODUCT IMAGE", product_image_path)]
        images.extend((f"DETAIL ROLE {role.upper()}", path) for role, path in generated_paths)
        audit = await self._vision_audit(
            images,
            (
                "Audit this three-image e-commerce detail set as a group. The scene image must show "
                "credible context, the feature image must emphasize a selling point with a deliberate "
                "feature composition, and the closeup image must show a source-supported macro detail. "
                "Score distinctiveness for meaningful visual differences and role_coverage for whether "
                "all three roles are actually fulfilled. Return JSON only: {\"passed\":true|false,"
                "\"distinctiveness\":0,\"role_coverage\":0,\"issues\":[],"
                "\"reason\":\"concise Chinese explanation\"}."
            ),
            DetailSetAudit,
        )
        audit["passed"] = (
            int(audit.get("distinctiveness", 0)) >= 75
            and int(audit.get("role_coverage", 0)) >= 75
        )
        return audit

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
        generation_context: GenerationContext | None = None,
        generation_mode: str = "standard",
    ) -> AssetOutput:
        """Run compliance + image gen + storage for one (platform, variant) tuple."""
        asset_platform = platform if not variant else f"{platform}:{variant}"
        from mediaforge.db import AssetStatus, get_engine, get_redis
        from mediaforge.db.job_store import JobStore

        store = JobStore(get_engine(), await get_redis())
        existing = await store.get_asset(
            job_id, sku.sku_id, self.output_type, asset_platform
        )
        if existing and existing["status"] == AssetStatus.success:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=existing["model_used"],
                platform=asset_platform,
                status="success",
                file_path=existing["file_path"],
            )

        checker = ComplianceChecker()
        storage = get_storage()
        sku_context = sku.model_dump()
        sku_context["_output_type"] = self.output_type
        sku_context["_current_platform"] = platform
        compliance = checker.check(sku_context, prompt)
        if generation_mode == "strict":
            compliance.modified_prompt += (
                " This is a corrective retry. Prioritize exact product identity, complete product "
                "visibility, correct platform background and composition over creative variation."
            )
            if variant == "feature":
                compliance.modified_prompt += (
                    " The previous result failed because it looked like a generic front-facing catalog "
                    "portrait. Do not repeat that composition. Make a visibly different selling-point "
                    "image: use a tighter shoulder-to-hip editorial crop, let the garment occupy most of "
                    "the frame, and use a natural pose or hand gesture to demonstrate a source-supported "
                    "fit, silhouette, hem, drape or construction benefit. Do not add text or callouts."
                )
            elif variant == "scene":
                compliance.modified_prompt += (
                    " The result must clearly show a credible environment and product-in-use context, "
                    "not a plain catalog background."
                )
            elif variant == "closeup":
                compliance.modified_prompt += (
                    " The result must be a true macro crop of one source-visible construction or material "
                    "detail, not a full or half-body catalog image."
                )
        elif generation_mode == "staged":
            compliance.modified_prompt += (
                " This is a product-fusion retry. Make the product fit the body or scene naturally, "
                "with realistic contact, folds, scale and occlusion while preserving every source detail."
            )
        if generation_context is not None:
            generation_context.prompts[asset_platform] = compliance.modified_prompt
        if compliance.blocked:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=platform,
                status="failed",
                error="L1 blocked",
            )
        if generation_context is not None:
            input_matches = generation_context.input_matches
            input_reason = generation_context.input_reason
        else:
            input_matches, input_reason, _ = await self._validate_product_input(
                sku, product_image_path
            )
        if not input_matches:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=asset_platform,
                status="failed",
                error=f"商品原图与商品信息不一致: {input_reason}",
            )
        saved_path: str | None = None
        try:
            effective_ref: str | bytes | None = ref_image_path
            strict_catalog_image = (
                self.output_type == "main_image" and platform.lower() == "amazon"
            ) or self.output_type == "pdd_white_background"
            if generation_mode == "staged" and not strict_catalog_image:
                stage_prompt = (
                    "Create a photorealistic e-commerce scene and natural model pose suitable "
                    f"for a {sku.product_name}. Establish the background, lighting, framing and "
                    "body pose only. Do not copy logos, text or the reference product. Leave the "
                    "garment/product area clear for an exact product fusion in the next step. "
                    f"Final composition guidance: {compliance.modified_prompt}"
                )
                effective_ref = await self.client.generate_image(
                    prompt=stage_prompt,
                    model=self.model,
                    size=sku.image_size,
                    aspect_ratio=aspect_ratio,
                    product_image_path=None,
                    ref_image_path=ref_image_path,
                )
            image_bytes = await self.client.generate_image(
                prompt=compliance.modified_prompt,
                model=self.model,
                size=sku.image_size,
                aspect_ratio=aspect_ratio,
                product_image_path=product_image_path,
                ref_image_path=effective_ref,
            )
            storage_image_bytes = await asyncio.to_thread(
                self._prepare_storage_image, image_bytes
            )
            asset_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"mediaforge:{job_id}:{sku.sku_id}:{self.output_type}:{platform}:"
                    f"{variant or ''}:{generation_mode}",
                )
            )
            saved_path = await storage.save_asset(
                tenant_id, job_id, asset_id, storage_image_bytes, ext="png"
            )
            quality = await self._validate_generated_image(
                sku=sku,
                platform=platform,
                aspect_ratio=aspect_ratio,
                image_size=sku.image_size,
                product_image_path=product_image_path,
                ref_image_path=ref_image_path,
                generated_image=image_bytes,
                product_attributes=(
                    generation_context.product_attributes if generation_context else None
                ),
                variant=variant,
            )
            export_checks = self._storage_image_checks(storage_image_bytes)
            quality["export_checks"] = export_checks
            if not export_checks["passed"]:
                quality["passed"] = False
                quality.setdefault("failed_checks", []).append(export_checks["reason"])
                quality["reason"] = "；".join(
                    filter(None, [str(quality.get("reason") or ""), export_checks["reason"]])
                )
            if generation_context is not None:
                generation_context.quality_results.append(
                    {
                        "asset": asset_platform,
                        "output_type": self.output_type,
                        "model": self.client.model_name(self.model),
                        "generation_mode": generation_mode,
                        **quality,
                    }
                )
            if not quality.get("passed"):
                error_text = (
                    "生成图质量检查未通过: "
                    + json.dumps(quality, ensure_ascii=False, separators=(",", ":"))
                )
                await store.add_asset(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    sku_id=sku.sku_id,
                    output_type=self.output_type,
                    model_used=self.client.model_name(self.model),
                    status=AssetStatus.failed,
                    file_path=saved_path,
                    platform=asset_platform,
                    error_msg=error_text,
                )
                return AssetOutput(
                    sku_id=sku.sku_id,
                    output_type=self.output_type,
                    model_used=self.client.model_name(self.model),
                    platform=asset_platform,
                    status="failed",
                    file_path=saved_path,
                    error=error_text,
                )
            await store.add_asset(
                job_id=job_id,
                tenant_id=tenant_id,
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                status=AssetStatus.success,
                file_path=saved_path,
                platform=asset_platform,
            )
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=asset_platform,
                status="success",
                file_path=saved_path,
            )
        except Exception as exc:
            return AssetOutput(
                sku_id=sku.sku_id,
                output_type=self.output_type,
                model_used=self.client.model_name(self.model),
                platform=asset_platform,
                status="failed",
                file_path=saved_path,
                error=str(exc),
            )

    def _prepare_storage_image(self, image_bytes: bytes) -> bytes:
        return image_bytes

    def _storage_image_checks(self, image_bytes: bytes) -> dict:
        return {"passed": True, "reason": ""}
