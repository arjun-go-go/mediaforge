import asyncio
import base64
import io
from pathlib import Path

import httpx
from langchain_community.embeddings import DashScopeEmbeddings
from loguru import logger

from mediaforge.config import get_settings

DASHSCOPE_MULTIMODAL_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/embeddings"
    "/multimodal-embedding/multimodal-embedding"
)


DASHSCOPE_RERANK_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


async def _image_to_data_uri(image_path: str) -> str:
    """Read a local image file and return a data:image/...;base64,... URI."""
    path = Path(image_path)
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}
    mime = mime_map.get(suffix, "jpeg")
    raw = await asyncio.to_thread(path.read_bytes)
    data = base64.b64encode(raw).decode()
    return f"data:image/{mime};base64,{data}"


def _bytes_to_data_uri(raw: bytes, max_px: int = 1024) -> str:
    from PIL import Image

    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert("RGB")
        width, height = image.size
        if max(width, height) > max_px:
            ratio = max_px / max(width, height)
            image = image.resize(
                (int(width * ratio), int(height * ratio)), Image.Resampling.LANCZOS
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"


class DashScopeEmbeddingClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.dashscope_api_key or settings.openrouter_api_key
        self.text_model = settings.dashscope_text_model
        self.image_model = settings.dashscope_image_model
        self.image_dim = settings.dashscope_image_dim
        self.rerank_model = settings.dashscope_rerank_model
        self._http_client: httpx.AsyncClient | None = None
        self._text_embedder = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60, trust_env=False)
        return self._http_client

    async def _normalize_image_input(self, image_path: str) -> str:
        if image_path.startswith("data:"):
            return image_path
        if image_path.startswith(("http://", "https://")):
            client = await self._get_http_client()
            response = await client.get(image_path, follow_redirects=True)
            response.raise_for_status()
            return await asyncio.to_thread(_bytes_to_data_uri, response.content)
        return await _image_to_data_uri(image_path)

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _text_emb(self):
        if self._text_embedder is None:
            self._text_embedder = DashScopeEmbeddings(
                model=self.text_model, dashscope_api_key=self.api_key
            )
        return self._text_embedder

    async def embed_text(self, text: str) -> list[float]:
        emb = self._text_emb()
        return await emb.aembed_query(text)

    async def embed_image(self, image_path: str) -> list[float]:
        """Embed an image via DashScope multimodal-embedding API.

        Args:
            image_path: Local file path or public URL.
        """
        # Determine if it's a URL or local file
        image_input = await self._normalize_image_input(image_path)

        payload = {
            "model": self.image_model,
            "input": {
                "contents": [{"image": image_input}],
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        client = await self._get_http_client()
        input_desc = (
            image_path if image_path.startswith(("http://", "https://")) else f"local:{image_path}"
        )
        logger.debug("→ DashScope embed_image  model={}  input={}", self.image_model, input_desc)
        t0 = asyncio.get_running_loop().time()
        resp = await client.post(DASHSCOPE_MULTIMODAL_URL, json=payload, headers=headers)
        elapsed = asyncio.get_running_loop().time() - t0
        if resp.status_code >= 400:
            detail = resp.text[:300]
            logger.warning(
                "← DashScope embed_image  FAILED  model={}  status={}  {:.2f}s  {}",
                self.image_model,
                resp.status_code,
                elapsed,
                detail,
            )
            resp.raise_for_status()
        logger.debug(
            "← DashScope embed_image  model={}  status={}  {:.2f}s",
            self.image_model,
            resp.status_code,
            elapsed,
        )
        body = resp.json()

        embedding = body["output"]["embeddings"][0]["embedding"]
        return embedding

    async def rerank(
        self,
        query_text: str,
        query_image_path: str | None,
        candidates: list[dict],
        top_n: int = 10,
    ) -> list[dict]:
        """Rerank candidates using DashScope qwen3-vl-rerank.

        Args:
            query_text: The user query text.
            query_image_path: Optional image URL or local path for visual reranking.
            candidates: List of dicts with at least a "text" key for reranking.
            top_n: Number of top results to return.

        Returns:
            Candidates sorted by relevance, with "rerank_score" added.
        """
        if not candidates:
            return candidates

        # Build documents list
        documents = []
        for c in candidates:
            doc: dict = {}
            if c.get("text"):
                doc["text"] = c["text"]
            if c.get("image_url"):
                doc["image"] = await self._normalize_image_input(c["image_url"])
            if not doc:
                doc["text"] = c.get("product_id", "")
            documents.append(doc)

        # Build query
        query: dict = {"text": query_text}
        if query_image_path:
            query["image"] = await self._normalize_image_input(query_image_path)

        payload = {
            "model": self.rerank_model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "return_documents": False,
                "top_n": min(top_n, len(candidates)),
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            client = await self._get_http_client()
            logger.debug(
                "→ DashScope rerank  model={}  candidates={}", self.rerank_model, len(candidates)
            )
            t0 = asyncio.get_running_loop().time()
            resp = await client.post(DASHSCOPE_RERANK_URL, json=payload, headers=headers)
            elapsed = asyncio.get_running_loop().time() - t0
            resp.raise_for_status()
            body = resp.json()
            logger.debug(
                "← DashScope rerank  model={}  status={}  {:.2f}s",
                self.rerank_model,
                resp.status_code,
                elapsed,
            )

            results = body["output"]["results"]
            reranked = []
            for r in results:
                idx = r["index"]
                item = dict(candidates[idx])
                item["rerank_score"] = r["relevance_score"]
                reranked.append(item)
            return reranked
        except Exception as exc:
            logger.warning(
                "← DashScope rerank  FAILED  model={}  {}  returning original order",
                self.rerank_model,
                exc,
            )
            return candidates
