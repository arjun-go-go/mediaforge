import asyncio
import base64
from typing import Literal, TypeVar

import httpx
from loguru import logger

from mediaforge.config import get_settings

StructuredResult = TypeVar("StructuredResult")

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
RETRYABLE_STATUS = {502, 503, 504, 429}


def _safe_payload_summary(payload: dict) -> str:
    """Return request metadata without prompts, user content, URLs or image bytes."""
    import json

    messages = payload.get("messages", [])
    image_count = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            image_count += sum(1 for item in content if item.get("type") == "image_url")
    image_count += sum(
        1 for item in payload.get("input_references", []) if item.get("type") == "image_url"
    )
    return json.dumps(
        {
            "model": payload.get("model"),
            "message_count": len(messages),
            "roles": [message.get("role") for message in messages],
            "tool_names": [
                tool.get("function", {}).get("name") for tool in payload.get("tools", [])
            ],
            "image_count": image_count,
            "stream": bool(payload.get("stream")),
        },
        ensure_ascii=False,
    )


async def _retry_request(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> dict:
    """POST with automatic retry on 5xx / rate-limit / network errors."""
    from mediaforge.workers.circuit_breaker import CircuitOpenError, circuit_breaker

    breaker = circuit_breaker("openrouter")
    if not breaker.allow_request():
        raise CircuitOpenError(breaker.name)

    model = payload.get("model", "?")
    logger.info(
        "→ OpenRouter  model={}  url={}\n  REQ {}", model, url, _safe_payload_summary(payload)
    )
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = asyncio.get_running_loop().time()
        try:
            resp = await client.post(url, headers=headers, json=payload)
            elapsed = asyncio.get_running_loop().time() - t0
            if resp.status_code in RETRYABLE_STATUS:
                raise httpx.HTTPStatusError(
                    f"Retryable status {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            logger.info(
                "← OpenRouter  model={}  status={}  {:.2f}s  tokens={}",
                model,
                resp.status_code,
                elapsed,
                usage.get("total_tokens", "?"),
            )
            breaker.record_success()
            return data
        except (
            httpx.HTTPStatusError,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
        ) as exc:
            elapsed = asyncio.get_running_loop().time() - t0
            err_body = ""
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    err_body = exc.response.text[:500]
                except Exception:
                    pass
            status_code = (
                exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            )
            can_retry = status_code is None or status_code in RETRYABLE_STATUS
            if attempt == MAX_RETRIES or not can_retry:
                logger.error(
                    "← OpenRouter  model={}  FAILED after {} attempts  {:.2f}s  {}\n  {}",
                    model,
                    attempt,
                    elapsed,
                    exc,
                    err_body,
                )
                if can_retry:
                    breaker.record_failure()
                if isinstance(exc, httpx.HTTPStatusError):
                    raise RuntimeError(
                        f"OpenRouter request failed ({status_code}): {err_body or str(exc)}"
                    ) from exc
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                "← OpenRouter  model={}  attempt {}/{}  status={}  retrying in {:.1f}s\n  {}",
                model,
                attempt,
                MAX_RETRIES,
                exc,
                wait,
                err_body,
            )
            await asyncio.sleep(wait)
    raise RuntimeError("Unreachable")


def _build_image_models() -> dict[str, str]:
    s = get_settings()
    return {
        "pro": s.image_model_pro,
        "fast": s.image_model_fast,
        "base": s.image_model_base,
    }


def _build_video_models() -> dict[str, str]:
    s = get_settings()
    return {"veo": s.video_model_veo, "seedance": s.video_model_seedance}


def get_image_models() -> dict[str, str]:
    return _build_image_models()


def get_video_models() -> dict[str, str]:
    return _build_video_models()


_VIDEO_SEMAPHORES: dict[str, asyncio.Semaphore] | None = None
_IMAGE_SEMAPHORES: dict[str, asyncio.Semaphore] | None = None


def _get_video_semaphores() -> dict[str, asyncio.Semaphore]:
    global _VIDEO_SEMAPHORES
    if _VIDEO_SEMAPHORES is None:
        s = get_settings()
        _VIDEO_SEMAPHORES = {
            s.video_model_veo: asyncio.Semaphore(s.semaphore_veo),
            s.video_model_seedance: asyncio.Semaphore(s.semaphore_seedance),
        }
    return _VIDEO_SEMAPHORES


def _get_image_semaphores() -> dict[str, asyncio.Semaphore]:
    global _IMAGE_SEMAPHORES
    if _IMAGE_SEMAPHORES is None:
        s = get_settings()
        _IMAGE_SEMAPHORES = {
            s.image_model_pro: asyncio.Semaphore(s.semaphore_gemini_pro_image),
            s.image_model_fast: asyncio.Semaphore(s.semaphore_gpt_image),
            s.image_model_base: asyncio.Semaphore(s.semaphore_gpt_image),
        }
    return _IMAGE_SEMAPHORES


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        s = get_settings()
        self.api_key = api_key or s.openrouter_api_key
        self.base_url = (base_url or s.openrouter_base_url).rstrip("/")

    def _headers(self) -> dict:
        s = get_settings()
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": s.site_url,
            "X-Title": s.site_title,
        }

    def model_name(self, alias: str) -> str:
        return get_image_models().get(alias, alias)

    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Generic chat completion through retry + circuit breaker."""
        s = get_settings()
        payload = {
            "model": model or s.agent_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        client = await self._get_client()
        data = await _retry_request(
            client,
            f"{self.base_url}/chat/completions",
            self._headers(),
            payload,
        )
        content = data["choices"][0]["message"].get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
            if text:
                return text
        raise ValueError("Chat completion returned no text content")

    async def structured_chat_completion(
        self,
        messages: list[dict],
        schema: type[StructuredResult],
        model: str | None = None,
        max_tokens: int = 800,
    ) -> StructuredResult:
        """Call OpenRouter with provider-enforced JSON Schema output.

        The OpenRouter SDK receives the same dedicated async client used by
        image generation. Its explicit proxy is isolated from the process and
        therefore cannot affect MinIO, PostgreSQL, Redis, or internal HTTP.
        """
        import openrouter
        from langchain_openrouter import ChatOpenRouter

        settings = get_settings()
        sync_client = httpx.Client(
            timeout=180.0,
            proxy=settings.http_proxy or None,
            trust_env=False,
            follow_redirects=True,
        )
        sdk_client = openrouter.OpenRouter(
            api_key=self.api_key,
            server_url=self.base_url,
            http_referer=settings.site_url,
            x_open_router_title=settings.site_title,
            client=sync_client,
            async_client=await self._get_client(),
        )
        llm = ChatOpenRouter(
            model=model or settings.quality_model,
            api_key=self.api_key,
            base_url=self.base_url,
            client=sdk_client,
            temperature=0,
            max_tokens=max_tokens,
            max_retries=2,
            reasoning={"effort": "low"},
            openrouter_provider={"require_parameters": True},
        )
        structured_llm = llm.with_structured_output(
            schema,
            method="json_schema",
            include_raw=True,
            strict=True,
        )
        try:
            result = await structured_llm.ainvoke(messages)
        finally:
            sync_client.close()

        parsed = result.get("parsed")
        if parsed is None:
            raw = result.get("raw")
            finish_reason = getattr(raw, "response_metadata", {}).get("finish_reason")
            parsing_error = result.get("parsing_error")
            raise ValueError(
                "OpenRouter structured output failed"
                f" (finish_reason={finish_reason}): {parsing_error}"
            )
        return parsed

    @staticmethod
    async def _encode_image(image_path: str | bytes, max_px: int = 1024) -> str:
        """Read a local or HTTP(S) image, resize it, and return base64 JPEG."""
        import io

        from PIL import Image as _Image

        if isinstance(image_path, bytes):
            source = io.BytesIO(image_path)
        elif image_path.startswith("/api/v1/files/"):
            from mediaforge.storage import get_storage

            object_key = image_path.removeprefix("/api/v1/files/")
            data = await get_storage().get_internal(object_key)
            if data is None:
                raise FileNotFoundError(f"MinIO object not found: {object_key}")
            source = io.BytesIO(data)
        elif image_path.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                response = await client.get(image_path, follow_redirects=True)
            response.raise_for_status()
            source = io.BytesIO(response.content)
        else:
            source = image_path

        def _resize(source, max_px: int) -> bytes:
            with _Image.open(source) as img:
                img = img.convert("RGB")
                w, h = img.size
                if max(w, h) > max_px:
                    ratio = max_px / max(w, h)
                    img = img.resize((int(w * ratio), int(h * ratio)), _Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()

        raw = await asyncio.to_thread(_resize, source, max_px)
        return base64.b64encode(raw).decode("utf-8")

    async def _image_payload(
        self,
        prompt: str,
        model: Literal["pro", "fast", "base"],
        size: str = "2K",
        aspect_ratio: str = "1:1",
        product_image_path: str | None = None,
        ref_image_path: str | None = None,
    ) -> dict:
        full_model = get_image_models()[model]
        references: list[dict] = []
        reference_notes: list[str] = []
        # Image 1: new product photo (if provided)
        if product_image_path:
            reference_notes.append(
                "Reference Image 1 is the authoritative SOURCE PRODUCT IMAGE. Preserve its "
                "category, silhouette, construction, color, material, patterns and distinctive "
                "details exactly."
            )
            b64 = await self._encode_image(product_image_path, max_px=1024)
            references.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        # Image 2: style reference photo (if provided)
        if ref_image_path:
            reference_number = len(references) + 1
            reference_notes.append(
                f"Reference Image {reference_number} is the STYLE REFERENCE IMAGE. Use only its "
                "composition, lighting, background, camera angle and mood. Never copy or "
                "substitute its product."
            )
            b64 = await self._encode_image(ref_image_path, max_px=1024)
            references.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )

        payload = {
            "model": full_model,
            "prompt": "\n\n".join([*reference_notes, prompt]),
            "n": 1,
            "aspect_ratio": aspect_ratio,
        }
        if references:
            payload["input_references"] = references
        if full_model == "openai/gpt-image-2":
            payload["quality"] = {"1K": "low", "2K": "medium", "4K": "high"}.get(
                size, "medium"
            )
        else:
            payload["resolution"] = size
        return payload

    async def _get_client(self) -> httpx.AsyncClient:
        from mediaforge.http_clients import get_openrouter_client

        return await get_openrouter_client()

    async def generate_image(
        self,
        prompt: str,
        model: Literal["pro", "fast", "base"] = "pro",
        size: str = "2K",
        aspect_ratio: str = "1:1",
        product_image_path: str | None = None,
        ref_image_path: str | None = None,
    ) -> bytes:
        full_model = get_image_models()[model]
        sem = _get_image_semaphores()[full_model]
        async with sem:
            payload = await self._image_payload(
                prompt, model, size, aspect_ratio, product_image_path, ref_image_path
            )
            client = await self._get_client()
            data = await _retry_request(
                client,
                f"{self.base_url}/images",
                self._headers(),
                payload,
            )
        return self._extract_image_bytes(data)

    @staticmethod
    def _extract_image_bytes(data: dict) -> bytes:
        for item in data.get("data") or []:
            encoded = item.get("b64_json")
            if encoded:
                return base64.b64decode(encoded)
        for choice in data.get("choices", []):
            message = choice.get("message", {})
            # Primary location: message["images"] (Gemini via OpenRouter)
            for item in message.get("images") or []:
                if item.get("type") == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:image"):
                        _, b64 = url.split(",", 1)
                        return base64.b64decode(b64)
            # Fallback: message["content"] list (other providers)
            for item in message.get("content") or []:
                if item.get("type") == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:image"):
                        _, b64 = url.split(",", 1)
                        return base64.b64decode(b64)
        raise ValueError("No image in OpenRouter response")

    async def generate_video(
        self,
        prompt: str,
        model: Literal["veo", "seedance"] = "veo",
        duration: int = 5,
        aspect_ratio: str = "9:16",
        ref_image_path: str | None = None,
    ) -> str:
        full_model = get_video_models()[model]
        sem = _get_video_semaphores()[full_model]
        async with sem:
            content = []
            if ref_image_path:
                b64 = await self._encode_image(ref_image_path)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
            content.append({"type": "text", "text": prompt})

            payload = {
                "model": full_model,
                "modalities": ["video", "text"],
                "messages": [{"role": "user", "content": content}],
                "video_config": {"duration": duration, "aspect_ratio": aspect_ratio},
            }

            client = await self._get_client()
            data = await _retry_request(
                client,
                f"{self.base_url}/chat/completions",
                self._headers(),
                payload,
            )
        return self._extract_video_url(data)

    @staticmethod
    def _extract_video_url(data: dict) -> str:
        for choice in data.get("choices", []):
            message = choice.get("message", {})
            for item in message.get("content", []):
                if item.get("type") == "video_url":
                    return item["video_url"]["url"]
        raise ValueError("No video URL in OpenRouter response")
