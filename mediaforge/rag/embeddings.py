import asyncio
import base64
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


def sparse_to_dict(sparse_row) -> dict[int, float]:
    """Convert a scipy sparse row to {col_index: value} dict for Milvus."""
    coo = sparse_row.tocoo()
    return {int(i): float(v) for i, v in zip(coo.col, coo.data)}


async def _image_to_data_uri(image_path: str) -> str:
    """Read a local image file and return a data:image/...;base64,... URI."""
    path = Path(image_path)
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}
    mime = mime_map.get(suffix, "jpeg")
    raw = await asyncio.to_thread(path.read_bytes)
    data = base64.b64encode(raw).decode()
    return f"data:image/{mime};base64,{data}"


class DashScopeEmbeddingClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.dashscope_api_key or settings.openrouter_api_key
        self.text_model = settings.dashscope_text_model
        self.image_model = settings.dashscope_image_model
        self.image_dim = settings.dashscope_image_dim
        self.rerank_model = settings.dashscope_rerank_model
        self._tfidf = None
        self._http_client: httpx.AsyncClient | None = None
        self._text_embedder = None
        self._load_tfidf()

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60)
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _text_emb(self):
        if self._text_embedder is None:
            self._text_embedder = DashScopeEmbeddings(model=self.text_model, dashscope_api_key=self.api_key)
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
        if image_path.startswith(("http://", "https://")):
            image_input = image_path
        else:
            image_input = await _image_to_data_uri(image_path)

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
        input_desc = image_path if image_path.startswith(("http://", "https://")) else f"local:{image_path}"
        logger.debug("→ DashScope embed_image  model={}  input={}", self.image_model, input_desc)
        t0 = asyncio.get_running_loop().time()
        resp = await client.post(DASHSCOPE_MULTIMODAL_URL, json=payload, headers=headers)
        elapsed = asyncio.get_running_loop().time() - t0
        if resp.status_code >= 400:
            detail = resp.text[:300]
            logger.warning(
                "← DashScope embed_image  FAILED  model={}  status={}  {:.2f}s  {}",
                self.image_model, resp.status_code, elapsed, detail,
            )
            resp.raise_for_status()
        logger.debug("← DashScope embed_image  model={}  status={}  {:.2f}s", self.image_model, resp.status_code, elapsed)
        body = resp.json()

        embedding = body["output"]["embeddings"][0]["embedding"]
        return embedding

    def build_tfidf(self, texts: list[str], max_features: int = 500):
        """Fit a TF-IDF vectorizer from the given texts and persist to disk."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._tfidf = TfidfVectorizer(stop_words="english", max_features=max_features)
        self._tfidf.fit(texts)
        self._save_tfidf()
        return self._tfidf

    def _tfidf_path(self) -> Path:
        return Path(get_settings().output_dir).resolve() / ".tfidf_vectorizer.joblib"

    def _save_tfidf(self) -> None:
        if self._tfidf is None:
            return
        import joblib
        path = self._tfidf_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._tfidf, path)

    def _load_tfidf(self) -> bool:
        path = self._tfidf_path()
        if not path.exists():
            return False
        try:
            import joblib
            self._tfidf = joblib.load(path)
            return True
        except Exception:
            return False

    def encode_sparse(self, text: str) -> dict[int, float]:
        """Transform a single text into a sparse vector dict using the fitted TF-IDF."""
        if self._tfidf is None:
            return {}
        row = self._tfidf.transform([text])
        return sparse_to_dict(row[0])

    def encode_sparse_batch(self, texts: list[str]) -> list[dict[int, float]]:
        """Transform multiple texts into sparse vector dicts."""
        if self._tfidf is None:
            return [{}] * len(texts)
        matrix = self._tfidf.transform(texts)
        return [sparse_to_dict(matrix[i]) for i in range(len(texts))]

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
                doc["image"] = c["image_url"]
            if not doc:
                doc["text"] = c.get("product_id", "")
            documents.append(doc)

        # Build query
        query: dict = {"text": query_text}
        if query_image_path:
            if query_image_path.startswith(("http://", "https://")):
                query["image"] = query_image_path
            else:
                query["image"] = await _image_to_data_uri(query_image_path)

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
            logger.debug("→ DashScope rerank  model={}  candidates={}", self.rerank_model, len(candidates))
            t0 = asyncio.get_running_loop().time()
            resp = await client.post(DASHSCOPE_RERANK_URL, json=payload, headers=headers)
            elapsed = asyncio.get_running_loop().time() - t0
            resp.raise_for_status()
            body = resp.json()
            logger.debug("← DashScope rerank  model={}  status={}  {:.2f}s", self.rerank_model, resp.status_code, elapsed)

            results = body["output"]["results"]
            reranked = []
            for r in results:
                idx = r["index"]
                item = dict(candidates[idx])
                item["rerank_score"] = r["relevance_score"]
                reranked.append(item)
            return reranked
        except Exception as exc:
            logger.warning("← DashScope rerank  FAILED  model={}  {}  returning original order", self.rerank_model, exc)
            return candidates

