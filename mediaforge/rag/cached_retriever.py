import hashlib
import json

from loguru import logger

from mediaforge.rag.models import RagResult
from mediaforge.rag.vector_store import VectorStore



def _cache_key(text: str, category: str, top_k: int, query_image: list[float] | None = None) -> str:
    img_sig = ""
    if query_image:
        img_sig = hashlib.sha256(json.dumps(query_image[:10]).encode()).hexdigest()[:12]
    raw = f"rag:{text}:{category}:{top_k}:{img_sig}"
    return f"mediaforge:rag_cache:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


class CachedRetriever:
    """Caching layer over VectorStore.

    Delegates to vector_store.hybrid_search() and caches results in Redis.
    Exposes the same retrieve() interface as ReferenceRetriever.
    """

    TTL_SECONDS = 600

    def __init__(self, vector_store: VectorStore, redis=None):
        self.vector_store = vector_store
        self.redis = redis

    async def retrieve(
        self,
        image_path: str | None,
        text: str,
        category: str,
        top_k: int = 5,
        query_dense: list[float] | None = None,
        query_sparse: dict[int, float] | None = None,
        query_image: list[float] | None = None,
    ) -> list[RagResult]:
        if self.redis is not None:
            key = _cache_key(text, category, top_k, query_image)
            try:
                cached = await self.redis.get(key)
                if cached:
                    items = json.loads(cached)
                    return [RagResult(**item) for item in items]
            except Exception as exc:
                logger.warning("RAG cache read failed: {}", exc)

        results = await self.vector_store.hybrid_search(
            image_path=image_path,
            text=text,
            category=category,
            top_k=top_k,
            query_dense=query_dense,
            query_sparse=query_sparse,
            query_image=query_image,
        )

        if self.redis is not None and results:
            key = _cache_key(text, category, top_k, query_image)
            try:
                payload = json.dumps([r.model_dump() for r in results])
                await self.redis.set(key, payload, ex=self.TTL_SECONDS)
            except Exception as exc:
                logger.warning("RAG cache write failed: {}", exc)

        return results
