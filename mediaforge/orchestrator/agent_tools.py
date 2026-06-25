import asyncio
import json
import tempfile
from pathlib import Path

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field


async def _download_to_temp(url: str) -> str | None:
    """Return a local path for an image, downloading it first if it's an HTTP URL."""
    if not url:
        return None
    local = Path(url)
    if local.is_absolute() and local.exists():
        return str(local)
    tmp_path = None
    try:
        from mediaforge.http_clients import get_openrouter_client
        client = await get_openrouter_client()
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        suffix = ".jpg"
        ct = resp.headers.get("content-type", "")
        if "png" in ct:
            suffix = ".png"
        elif "webp" in ct:
            suffix = ".webp"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        tmp.write(resp.content)
        tmp.close()
        return tmp_path
    except Exception:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        return None


def _is_downloaded_temp(original_url: str, resolved_path: str) -> bool:
    """True when resolved_path was downloaded (and should be cleaned up), False for local originals."""
    if not original_url or not resolved_path:
        return False
    return not Path(original_url).is_absolute() and resolved_path != original_url


# ---------------------------------------------------------------------------
# P0: StyleAnalyzerTool — LLM reads reference images and produces a style prompt
# ---------------------------------------------------------------------------

class AnalyzeStyleInput(BaseModel):
    ref_image_url: str = Field(description="风格参考图的 URL 或本地路径（来自 RAG 检索）")
    product_description: str = Field(default="", description="新产品的简要文字描述，帮助 LLM 聚焦风格分析")


class StyleAnalyzerTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "analyze_style"
    description: str = (
        "分析参考图片的视觉风格（场景、光线、构图、氛围），"
        "返回一段可直接用于生图的英文 style prompt（100 词以内）。"
        "有参考图时务必先调用此工具，再调用 generate_image。"
    )
    args_schema: type[BaseModel] = AnalyzeStyleInput

    async def _arun(self, ref_image_url: str, product_description: str = "") -> str:
        from mediaforge.config import get_settings
        from mediaforge.workers.openrouter_client import OpenRouterClient

        ref_path = await _download_to_temp(ref_image_url)
        if not ref_path:
            return "无法加载参考图，请直接使用文字描述生图。"

        b64 = await _encode_resized(ref_path, max_px=512)
        is_temp = _is_downloaded_temp(ref_image_url, ref_path)
        try:
            content = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": (
                        "This is a reference product photo from a bestselling catalog.\n\n"
                        + (f"New product description: {product_description}\n\n" if product_description else "")
                        + "Analyze the visual style of this reference photo across these dimensions:\n"
                        "1. Scene / background setting\n"
                        "2. Lighting and color tone\n"
                        "3. Model pose and framing\n"
                        "4. Overall mood and aesthetic\n\n"
                        "Then write ONE concise image generation prompt (under 100 words) "
                        "that captures this style for a new product. "
                        "Output ONLY the prompt, nothing else."
                    ),
                },
            ]
            client = OpenRouterClient(api_key=get_settings().openrouter_api_key)
            style_prompt = await client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert e-commerce visual stylist. "
                            "Output ONLY the final English image generation prompt. "
                            "Do NOT include any explanations, markdown, or prefixes like 'Here is the prompt'. "
                            "Maximum 100 words."
                        ),
                    },
                    {"role": "user", "content": content},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            return style_prompt if style_prompt else "Style analysis failed; use text description only."
        except Exception as exc:
            from loguru import logger
            logger.error("Style analysis failed: {}", exc)
            return "Style analysis failed due to API error; use text description only."
        finally:
            if is_temp:
                Path(ref_path).unlink(missing_ok=True)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


# ---------------------------------------------------------------------------
# Shared image encode helper (P2: resize before base64)
# ---------------------------------------------------------------------------

async def _encode_resized(image_path: str, max_px: int = 1024) -> str:
    """Read an image, resize so the longest side ≤ max_px, return base64 JPEG string."""
    import io
    from PIL import Image

    def _resize_bytes(path: str, max_px: int) -> bytes:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_px:
                ratio = max_px / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()

    raw = await asyncio.to_thread(_resize_bytes, image_path, max_px)
    import base64
    return base64.b64encode(raw).decode("utf-8")


# ---------------------------------------------------------------------------
# GenerateImageTool (P1: added product_image_url)
# ---------------------------------------------------------------------------

class GenerateImageInput(BaseModel):
    prompt: str = Field(description="图片生成提示词（建议使用英文以获得最佳效果）")
    model: str = Field(default="pro", description="图片模型档位:pro(Gemini 3 Pro Image,高质量)或 fast(GPT-5.4 Image 2,快速)")
    size: str = Field(default="2K", description="分辨率：1K、2K 或 4K")
    aspect_ratio: str = Field(default="1:1", description="宽高比，如 1:1、3:4、16:9")
    product_image_url: str = Field(default="", description="可选的新品产品图 URL 或本地路径，作为 Image 1 传给模型")
    ref_image_url: str = Field(default="", description="可选的风格参考图 URL，通常来自 RAG 检索或 analyze_style，作为 Image 2 传给模型")


class GenerateImageTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "generate_image"
    description: str = (
        "通过 OpenRouter 生成电商产品图。"
        "可传入 product_image_url（新品图）和 ref_image_url（风格参考图）同时作为参考。"
        "如果有参考图，建议先调用 analyze_style 获取 style prompt 再调用此工具。"
    )
    args_schema: type[BaseModel] = GenerateImageInput

    async def _arun(
        self,
        prompt: str,
        model: str = "pro",
        size: str = "2K",
        aspect_ratio: str = "1:1",
        product_image_url: str = "",
        ref_image_url: str = "",
    ) -> str:
        from mediaforge.workers.openrouter_client import OpenRouterClient
        from mediaforge.config import get_settings

        async def _maybe_download(url: str) -> str | None:
            return await _download_to_temp(url) if url else None

        results = await asyncio.gather(
            _maybe_download(product_image_url),
            _maybe_download(ref_image_url),
            return_exceptions=True,
        )
        product_path = results[0] if not isinstance(results[0], BaseException) else None
        ref_path = results[1] if not isinstance(results[1], BaseException) else None
        is_temp_product = _is_downloaded_temp(product_image_url, product_path) if product_path else False
        is_temp_ref = _is_downloaded_temp(ref_image_url, ref_path) if ref_path else False
        try:
            client = OpenRouterClient(api_key=get_settings().openrouter_api_key)
            data = await client.generate_image(
                prompt=prompt,
                model=model,
                size=size,
                aspect_ratio=aspect_ratio,
                product_image_path=product_path,
                ref_image_path=ref_path,
            )
            import hashlib as _hl
            filename_stem = f"{model}_{_hl.sha256(prompt.encode()).hexdigest()[:16]}"
            from mediaforge.storage import get_storage
            storage = get_storage()
            location = await storage.save_asset(
                tenant_id="agent",
                job_id=model,
                asset_id=filename_stem,
                data=data,
                ext="png",
            )
            url = location if location.startswith("http") else f"/outputs/{location}"
            return json.dumps({"status": "success", "type": "image", "url": url})
        except Exception as exc:
            from loguru import logger
            logger.error("GenerateImageTool failed: {}", exc)
            return json.dumps({"status": "error", "message": str(exc)})
        finally:
            if is_temp_product and product_path:
                Path(product_path).unlink(missing_ok=True)
            if is_temp_ref and ref_path:
                Path(ref_path).unlink(missing_ok=True)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


class GenerateVideoInput(BaseModel):
    prompt: str = Field(description="视频生成提示词（建议使用英文以获得最佳效果）")
    model: str = Field(default="veo", description="视频模型:veo(Google Veo 3.1)或 seedance(Seedance 2.0,字节跳动)")
    duration: int = Field(default=5, description="视频时长（秒）")
    ref_image_url: str = Field(default="", description="可选的视觉参考图 URL，通常来自 RAG 检索结果")


class GenerateVideoTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "generate_video"
    description: str = "通过 OpenRouter 生成产品展示短视频。可传入 ref_image_url（来自 RAG 检索）作为视觉参考。"
    args_schema: type[BaseModel] = GenerateVideoInput

    async def _arun(
        self,
        prompt: str,
        model: str = "veo",
        duration: int = 5,
        ref_image_url: str = "",
    ) -> str:
        from mediaforge.workers.openrouter_client import OpenRouterClient
        from mediaforge.config import get_settings

        ref_path = await _download_to_temp(ref_image_url) if ref_image_url else None
        is_temp = _is_downloaded_temp(ref_image_url, ref_path) if ref_path else False
        try:
            client = OpenRouterClient(api_key=get_settings().openrouter_api_key)
            url = await client.generate_video(
                prompt=prompt, model=model, duration=duration,
                ref_image_path=ref_path,
            )
            return json.dumps({"status": "success", "type": "video", "url": url})
        finally:
            if is_temp and ref_path:
                Path(ref_path).unlink(missing_ok=True)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")


_compliance_checker = None


def _get_compliance_checker():
    global _compliance_checker
    if _compliance_checker is None:
        from mediaforge.workers.compliance.checker import ComplianceChecker
        _compliance_checker = ComplianceChecker()
    return _compliance_checker


class CheckComplianceInput(BaseModel):
    prompt: str = Field(description="待审查的提示词")
    market: str = Field(default="US", description="目标市场代码，如 US、CN、JP、EU")


class CheckComplianceTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "check_compliance"
    description: str = "检查提示词是否符合目标市场的文化与平台合规要求（如宗教禁忌、平台审核规则等）。"
    args_schema: type[BaseModel] = CheckComplianceInput

    async def _arun(self, prompt: str, market: str = "US") -> str:
        checker = _get_compliance_checker()

        def _sync_check():
            return checker.check({"market": market, "output_types": ["main_image"]}, prompt)

        try:
            result = await asyncio.to_thread(_sync_check)
        except Exception as exc:
            from loguru import logger
            logger.error("Compliance check failed: {}", exc)
            return "合规检查服务暂时不可用，请人工复核。"

        if result.blocked:
            return json.dumps({"status": "blocked", "reason": "提示词未通过合规审查"})
        return json.dumps({
            "status": "approved",
            "warnings": result.warnings,
            "modified_prompt": result.modified_prompt,
        })

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")
