import asyncio
import json
import re
import uuid

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_compliance_checker = None
AGENT_TOOLSET_VERSION = "2026-08-07.8"


def _uploaded_product_name(image_stem: str) -> str:
    generated_name = re.fullmatch(
        r"(?:clipboard|pasted|upload(?:ed)?(?:[-_]?product)?|image|img)[-_]?(?:\d+|[0-9a-f-]{8,})?",
        image_stem,
        re.IGNORECASE,
    )
    return "用户上传商品" if generated_name else image_stem


def tool_error(code: str, message: str, *, retryable: bool = False) -> str:
    return json.dumps(
        {
            "ok": False,
            "error_code": code,
            "message": message,
            "retryable": retryable,
        },
        ensure_ascii=False,
    )


def _get_compliance_checker():
    global _compliance_checker
    if _compliance_checker is None:
        from mediaforge.workers.compliance.checker import ComplianceChecker

        _compliance_checker = ComplianceChecker()
    return _compliance_checker


class CheckComplianceInput(BaseModel):
    prompt: str = Field(description="待审查的提示词")
    platform: str = Field(description="目标平台，如 amazon、shein、temu；不得自行默认")
    output_type: str = Field(
        default="main_image",
        description="main_image、detail_page 或 pdd_white_background",
    )
    category: str = Field(default="general", description="商品品类")
    market: str = Field(default="auto", description="目标市场代码；auto 时根据平台推导")

    @field_validator("platform")
    @classmethod
    def _validate_platform(cls, value: str) -> str:
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        platform = value.strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"不支持的平台: {platform}")
        return platform

    @field_validator("output_type")
    @classmethod
    def _validate_output_type(cls, value: str) -> str:
        if value not in {"main_image", "detail_page", "pdd_white_background"}:
            raise ValueError(f"不支持的输出类型: {value}")
        return value


class CheckComplianceTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "check_compliance"
    description: str = "按商品品类、目标平台、输出类型和市场检查营销提示词。"
    args_schema: type[BaseModel] = CheckComplianceInput

    async def _arun(
        self,
        prompt: str,
        platform: str,
        output_type: str = "main_image",
        category: str = "general",
        market: str = "auto",
    ) -> str:
        from mediaforge.workers.platform_rules import infer_market

        checker = _get_compliance_checker()
        platform = platform.strip().lower()
        market = infer_market([platform]) if market.lower() == "auto" else market.upper()

        def _sync_check():
            return checker.check(
                {
                    "market": market,
                    "category": category,
                    "target_platforms": [platform],
                    "output_types": [output_type],
                    "_current_platform": platform,
                    "_output_type": output_type,
                },
                prompt,
            )

        try:
            result = await asyncio.to_thread(_sync_check)
        except Exception as exc:
            from loguru import logger

            logger.error("Compliance check failed: {}", exc)
            return tool_error(
                "COMPLIANCE_UNAVAILABLE",
                "合规检查服务暂时不可用，请人工复核。",
                retryable=True,
            )

        if result.blocked:
            return json.dumps(
                {"status": "blocked", "reason": "提示词未通过合规审查"},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "approved",
                "warnings": result.warnings,
                "modified_prompt": result.modified_prompt,
            },
            ensure_ascii=False,
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


class ImageComplianceResult(BaseModel):
    compliant: bool
    product_visible: bool
    background_compliant: bool
    has_prohibited_overlay: bool
    issues: list[str] = Field(default_factory=list)
    summary: str


class CheckImageComplianceInput(BaseModel):
    image_url: str = Field(description="待检查商品图片的可信 MinIO 或商品库 URL")
    platform: str = Field(description="目标电商平台；不得自行默认")
    output_type: str = Field(default="main_image", description="main_image、detail_page 或 pdd_white_background")
    category: str = Field(default="general", description="商品品类")


class CheckImageComplianceTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "check_image_compliance"
    description: str = (
        "使用视觉模型检查一张实际商品图片是否符合目标平台的图片规则。"
        "只用于图片视觉合规；营销文字或生图提示词应使用 check_compliance。"
    )
    args_schema: type[BaseModel] = CheckImageComplianceInput
    tenant_id: str = ""

    def __init__(self, tenant_id: str, **kwargs):
        super().__init__(tenant_id=tenant_id, **kwargs)

    async def _trusted_image(self, image_url: str) -> bool:
        from sqlalchemy import or_, select

        from mediaforge.config import get_settings
        from mediaforge.db.engine import get_engine
        from mediaforge.db.tables import ProductTable

        settings = get_settings()
        upload_prefix = f"{settings.minio_public_base_url.rstrip('/')}/uploads/{self.tenant_id}/"
        if image_url.startswith(upload_prefix):
            return True
        table = ProductTable.__table__
        async with get_engine().connect() as connection:
            row = (
                await connection.execute(
                    select(table.c.sku_code)
                    .where(
                        table.c.image_url == image_url,
                        or_(table.c.visibility == "global", table.c.tenant_id == uuid.UUID(self.tenant_id)),
                    )
                    .limit(1)
                )
            ).first()
        return row is not None

    async def _arun(
        self,
        image_url: str,
        platform: str,
        output_type: str = "main_image",
        category: str = "general",
    ) -> str:
        from mediaforge.config import get_settings
        from mediaforge.workers.openrouter_client import OpenRouterClient
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS, get_platform_rule

        platform = platform.strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            return tool_error("UNSUPPORTED_PLATFORM", f"不支持的平台: {platform}")
        if output_type not in {"main_image", "detail_page", "pdd_white_background"}:
            return tool_error("UNSUPPORTED_OUTPUT_TYPE", f"不支持的输出类型: {output_type}")
        if not await self._trusted_image(image_url):
            return tool_error("INVALID_IMAGE_SOURCE", "图片不是当前企业上传文件或可访问的商品库图片")

        rule = get_platform_rule(platform)
        audit_rule = rule.detail_audit if output_type == "detail_page" else rule.main_audit
        try:
            encoded = await OpenRouterClient._encode_image(image_url, max_px=768)
            content = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                {
                    "type": "text",
                    "text": (
                        f"Audit this real e-commerce image for platform={platform}, "
                        f"output_type={output_type}, category={category}. Rule: {audit_rule} "
                        "Judge only visible evidence. Return concise Chinese findings."
                    ),
                },
            ]
            result = await OpenRouterClient().structured_chat_completion(
                messages=[{"role": "user", "content": content}],
                schema=ImageComplianceResult,
                model=get_settings().quality_model,
                max_tokens=600,
            )
            return json.dumps(result.model_dump(), ensure_ascii=False)
        except Exception as exc:
            from loguru import logger

            logger.error("Image compliance check failed: {}", exc)
            return tool_error("IMAGE_COMPLIANCE_UNAVAILABLE", "图片视觉合规检查暂时不可用，请稍后重试", retryable=True)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


class GetAgentCapabilitiesInput(BaseModel):
    pass


class GetAgentCapabilitiesTool(BaseTool):
    name: str = "get_agent_capabilities"
    description: str = "查询 MediaForge 智能助手、图片生成和质量检查实际使用的模型与支持能力。"
    args_schema: type[BaseModel] = GetAgentCapabilitiesInput

    async def _arun(self) -> str:
        from mediaforge.config import get_settings
        from mediaforge.workers.openrouter_client import get_image_models
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        settings = get_settings()
        return json.dumps(
            {
                "agent_model": settings.agent_model,
                "agent_fallback_model": settings.agent_fallback_model,
                "quality_model": settings.quality_model,
                "image_models": get_image_models(),
                "platforms": sorted(SUPPORTED_PLATFORMS),
                "output_types": ["main_image", "detail_page", "pdd_white_background"],
            },
            ensure_ascii=False,
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


class SubmitGenerationInput(BaseModel):
    sku_id: str = Field(default="", description="商品 SKU；已有可信会话商品上下文时可省略")
    product_image_url: str = Field(default="", description="商品原图 URL；已有可信会话商品上下文时可省略")
    product_name: str = Field(default="", description="商品名称；已有可信会话商品上下文时可省略")
    category: str = Field(default="", description="商品品类；已有可信会话商品上下文时可省略")
    target_platforms: list[str] = Field(
        default_factory=list,
        description="目标平台；优先使用可信会话上下文，缺失时先询问用户，不得默认 Amazon",
    )
    output_types: list[str] = Field(default_factory=lambda: ["main_image"])
    style_hint: str | None = None
    presentation_mode: str = Field(
        default="auto", description="展示方式:auto、model_wear 或 product_only"
    )
    model_preference: str = Field(
        default="auto", description="模特偏好:auto、female、male 或 no_face"
    )
    market: str = Field(default="auto", description="auto 时根据首个目标平台推导")
    ref_sku_id: str | None = None
    image_model: str = "fast"
    aspect_ratio: str = "auto"
    image_size: str = "2K"
    priority: str = "normal"
    source_mode: str = Field(
        default="active",
        description="商品原图来源：active、uploaded 或 catalog。用户说使用上面上传图片时选 uploaded",
    )

    @field_validator("target_platforms")
    @classmethod
    def _validate_platforms(cls, value: list[str]) -> list[str]:
        from mediaforge.workers.platform_rules import SUPPORTED_PLATFORMS

        platforms = [item.strip().lower() for item in value if item.strip()]
        unsupported = sorted(set(platforms) - SUPPORTED_PLATFORMS)
        if unsupported:
            raise ValueError(f"不支持的平台: {', '.join(unsupported)}")
        return platforms

    @field_validator("output_types")
    @classmethod
    def _validate_outputs(cls, value: list[str]) -> list[str]:
        allowed = {"main_image", "detail_page", "pdd_white_background"}
        outputs = [item.strip() for item in value if item.strip()]
        unsupported = sorted(set(outputs) - allowed)
        if not outputs:
            raise ValueError("至少选择一种输出类型")
        if unsupported:
            raise ValueError(f"不支持的输出类型: {', '.join(unsupported)}")
        return outputs

    @model_validator(mode="after")
    def _validate_pdd_white_background(self):
        if "pdd_white_background" in self.output_types and "pinduoduo" not in self.target_platforms:
            raise ValueError("拼多多白底图只能用于 pinduoduo 平台")
        return self


class SubmitGenerationJobTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "submit_generation_job"
    description: str = (
        "准备电商图片生成任务并返回待确认卡片。此工具不会直接创建付费任务；"
        "用户必须在页面点击确认后才由后端提交。"
    )
    args_schema: type[BaseModel] = SubmitGenerationInput
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = "default"

    def __init__(self, tenant_id: str, user_id: str, session_id: str, **kwargs):
        super().__init__(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            **kwargs,
        )

    async def _arun(self, **kwargs) -> str:
        from mediaforge.config import get_settings
        from mediaforge.db.redis_client import get_redis
        from mediaforge.models.job import BatchSubmitPayload, SkuInput
        from mediaforge.workers.platform_rules import infer_market

        try:
            from sqlalchemy import case, or_, select

            from mediaforge.db.engine import get_engine
            from mediaforge.db.tables import AgentSessionTable, ProductTable

            session_table = AgentSessionTable.__table__
            async with get_engine().connect() as connection:
                session_context = (
                    await connection.execute(
                        select(session_table.c.context).where(
                            session_table.c.tenant_id == uuid.UUID(self.tenant_id),
                            session_table.c.user_id == uuid.UUID(self.user_id),
                            session_table.c.session_id == self.session_id,
                        )
                    )
                ).scalar_one_or_none() or {}

            source_mode = str(kwargs.pop("source_mode", "active") or "active").lower()
            active_source = session_context.get("active_source")
            use_uploaded = source_mode == "uploaded" or (
                source_mode == "active" and active_source == "uploaded_product"
            )
            uploaded_product = session_context.get("uploaded_product") or {}
            selected_product = session_context.get("selected_product") or {}
            if use_uploaded and uploaded_product.get("image_url"):
                image_name = str(uploaded_product.get("image_name") or "uploaded_product")
                image_stem = image_name.rsplit(".", 1)[0]
                kwargs["product_image_url"] = uploaded_product["image_url"]
                # Uploaded-product identity must never inherit fields from the
                # separately selected bestseller reference.
                kwargs["sku_id"] = str(uploaded_product.get("sku_id") or image_stem)
                kwargs["product_name"] = str(
                    uploaded_product.get("product_name") or _uploaded_product_name(image_stem)
                )
                kwargs["category"] = str(uploaded_product.get("category") or "general")
                if not kwargs.get("ref_sku_id") and selected_product.get("sku_code"):
                    kwargs["ref_sku_id"] = selected_product["sku_code"]
            elif selected_product.get("sku_code") and not kwargs.get("sku_id"):
                kwargs["sku_id"] = selected_product["sku_code"]

            table = ProductTable.__table__
            visible = or_(
                table.c.visibility == "global",
                table.c.tenant_id == uuid.UUID(self.tenant_id),
            )
            trusted_product = None
            if not use_uploaded:
                async with get_engine().connect() as connection:
                    trusted_product = (
                        await connection.execute(
                            select(
                                table.c.sku_code,
                                table.c.image_url,
                                table.c.category,
                            )
                            .where(visible, table.c.sku_code == kwargs["sku_id"])
                            .order_by(
                                case(
                                    (table.c.tenant_id == uuid.UUID(self.tenant_id), 0),
                                    else_=1,
                                )
                            )
                            .limit(1)
                        )
                    ).mappings().first()

            if trusted_product:
                kwargs["product_image_url"] = trusted_product["image_url"]
                kwargs["category"] = trusted_product["category"]
                kwargs["product_name"] = trusted_product["sku_code"]
            elif not use_uploaded:
                settings = get_settings()
                upload_prefix = (
                    f"{settings.minio_public_base_url.rstrip('/')}/uploads/{self.tenant_id}/"
                )
                if not str(kwargs.get("product_image_url") or "").startswith(upload_prefix):
                    return tool_error(
                        "INVALID_PRODUCT_SOURCE",
                        "商品不存在或商品图片不是当前企业上传的文件",
                    )

            target_platforms = kwargs.get("target_platforms") or []
            if not target_platforms and session_context.get("target_platform"):
                target_platforms = [session_context["target_platform"]]
            if not target_platforms:
                return tool_error(
                    "TARGET_PLATFORM_REQUIRED",
                    "请选择目标电商平台后再准备生成任务",
                )
            market = kwargs.get("market", "auto")
            if not market or market.lower() == "auto":
                market = infer_market(target_platforms)
            payload = BatchSubmitPayload(
                skus=[
                    SkuInput(
                        sku_id=kwargs["sku_id"],
                        product_image_url=kwargs["product_image_url"],
                        product_name=kwargs["product_name"],
                        category=kwargs["category"],
                        target_platforms=target_platforms,
                        output_types=kwargs.get("output_types", ["main_image"]),
                        style_hint=kwargs.get("style_hint"),
                        presentation_mode=kwargs.get("presentation_mode", "auto"),
                        model_preference=kwargs.get("model_preference", "auto"),
                        market=market.upper(),
                        ref_sku_id=kwargs.get("ref_sku_id"),
                        reference_mode="specified" if kwargs.get("ref_sku_id") else "auto",
                        aspect_ratio=kwargs.get("aspect_ratio", "auto"),
                        image_size=kwargs.get("image_size", "2K"),
                    )
                ],
                image_model=kwargs.get("image_model", "fast"),
                video_model="veo",
                priority=kwargs.get("priority", "normal"),
            )
            confirmation_id = str(uuid.uuid4())
            pending = {
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "payload": payload.model_dump(mode="json"),
            }
            settings = get_settings()
            from mediaforge.orchestrator.agent_prompt import get_prompt

            prompt_version, prompt_hash, _ = get_prompt(settings.agent_prompt_version)
            agent_release = {
                "prompt_version": prompt_version,
                "prompt_hash": prompt_hash,
                "toolset_version": AGENT_TOOLSET_VERSION,
                "agent_model": settings.agent_model,
                "agent_temperature": settings.agent_temperature,
            }
            pending["agent_release"] = agent_release
            redis = await get_redis()
            await redis.setex(
                f"agent:confirmation:{self.tenant_id}:{self.user_id}:{confirmation_id}",
                settings.agent_confirmation_ttl_seconds,
                json.dumps(pending, ensure_ascii=False),
            )
            from mediaforge.db.audit_store import audit

            await audit(
                "agent_job_prepared",
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                metadata={
                    "confirmation_id": confirmation_id,
                    "session_id": self.session_id,
                    "sku_id": payload.skus[0].sku_id,
                    **agent_release,
                },
            )
            sku = payload.skus[0]
            return json.dumps(
                {
                    "status": "confirmation_required",
                    "confirmation_id": confirmation_id,
                    "expires_in": settings.agent_confirmation_ttl_seconds,
                    "summary": {
                        "sku_id": sku.sku_id,
                        "product_name": sku.product_name,
                        "platforms": sku.target_platforms,
                        "output_types": sku.output_types,
                        "image_model": payload.image_model.value,
                        "image_size": sku.image_size,
                        "aspect_ratio": sku.aspect_ratio,
                        "presentation_mode": sku.presentation_mode,
                        "model_preference": sku.model_preference,
                        "style_hint": sku.style_hint,
                        "reference_mode": sku.reference_mode,
                        "ref_sku_id": sku.ref_sku_id,
                    },
                },
                ensure_ascii=False,
            )
        except Exception:
            return tool_error(
                "JOB_PREPARATION_FAILED",
                "任务配置暂时无法保存，请稍后重试",
                retryable=True,
            )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


class GetGenerationJobInput(BaseModel):
    job_id: str = Field(description="生成任务 ID")


class GetGenerationJobTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_generation_job"
    description: str = "查询当前企业生成任务的进度、生成图片、失败原因和质量检查结果。"
    args_schema: type[BaseModel] = GetGenerationJobInput
    tenant_id: str = ""

    def __init__(self, tenant_id: str, **kwargs):
        super().__init__(tenant_id=tenant_id, **kwargs)

    async def _arun(self, job_id: str) -> str:
        from mediaforge.db.engine import get_engine
        from mediaforge.db.job_store import JobStore
        from mediaforge.db.redis_client import get_redis

        store = JobStore(get_engine(), await get_redis())
        try:
            job = await store.get_job(job_id)
            if str(job["tenant_id"]) != self.tenant_id:
                return tool_error("JOB_NOT_FOUND", "任务不存在")
            assets = await store.get_assets_for_job(job_id)
            items = await store.get_job_items(job_id)
            asset_results = [
                {
                    "sku_id": asset["sku_id"],
                    "output_type": asset["output_type"],
                    "platform": asset.get("platform"),
                    "status": str(asset["status"]),
                    "image_url": asset.get("file_path"),
                    "model_used": asset.get("model_used"),
                    "error": asset.get("error_msg"),
                }
                for asset in assets
            ]
            item_results = []
            for item in items:
                context = item.get("generation_context") or {}
                item_results.append(
                    {
                        "sku_id": item["sku_id"],
                        "status": item["status"],
                        "error": item.get("error_msg"),
                        "quality_results": context.get("quality_results", []),
                    }
                )
            return json.dumps(
                {
                    "job_id": job_id,
                    "status": str(job["status"]),
                    "done_skus": job["done_skus"],
                    "total_skus": job["total_skus"],
                    "task_url": f"/tasks?jobId={job_id}",
                    "assets": asset_results,
                    "items": item_results,
                },
                ensure_ascii=False,
            )
        except Exception:
            return tool_error(
                "JOB_QUERY_FAILED",
                "任务查询失败或任务不存在",
                retryable=True,
            )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")
