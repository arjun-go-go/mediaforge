import asyncio
from typing import Any

from pymilvus import AnnSearchRequest, DataType, MilvusClient, RRFRanker
from loguru import logger

from mediaforge.rag.models import RagItem, RagResult
from mediaforge.rag.vector_store import VectorStore


import re

_CATEGORY_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,64}$")


def _build_category_filter(category: str | None) -> str:
    """Return a Milvus filter expression. Empty when category is missing or rejected.

    Strict allowlist protects against expression injection — any caller-supplied
    category that contains characters outside ``[a-zA-Z0-9_-]`` is silently
    dropped from the filter instead of being quoted into the expression.
    """
    if not category:
        return ""
    if not _CATEGORY_RE.match(category):
        logger.warning("Rejected category filter (invalid chars): {!r}", category)
        return ""
    return f'category == "{category}"'



class MilvusVectorStore(VectorStore):
    def __init__(self, uri: str, collection: str = "mediaforge",
                 text_dim: int = 1024, image_dim: int = 1024,
                 token: str = "", db_name: str = "default"):
        self.uri = uri
        self.token = token
        self.db_name = db_name
        self.collection = collection
        self.text_dim = text_dim
        self.image_dim = image_dim
        self._client = None
        self._collection_ready = False
        self._init_lock = asyncio.Lock()

    def _ensure_client(self) -> MilvusClient:
        if self._client is None:
            kwargs: dict[str, Any] = {"uri": self.uri}
            if self.token:
                kwargs["token"] = self.token
            if self.db_name and self.db_name != "default":
                kwargs["db_name"] = self.db_name
            self._client = MilvusClient(**kwargs)
        return self._client

    def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        client = self._ensure_client()
        if not client.has_collection(self.collection):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
            schema.add_field("product_id", DataType.VARCHAR, max_length=64, is_primary=True)
            schema.add_field("category", DataType.VARCHAR, max_length=64)
            schema.add_field("style", DataType.VARCHAR, max_length=64)
            schema.add_field("color", DataType.VARCHAR, max_length=64)
            schema.add_field("material", DataType.VARCHAR, max_length=64)
            schema.add_field("image_url", DataType.VARCHAR, max_length=512)
            schema.add_field("text_vector", DataType.FLOAT_VECTOR, dim=self.text_dim)
            schema.add_field("image_vector", DataType.FLOAT_VECTOR, dim=self.image_dim)
            schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)

            index_params = client.prepare_index_params()
            index_params.add_index(field_name="text_vector", index_type="FLAT", metric_type="COSINE")
            index_params.add_index(field_name="image_vector", index_type="FLAT", metric_type="COSINE")
            index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")

            client.create_collection(self.collection, schema=schema, index_params=index_params)
        self._collection_ready = True

    async def _init(self) -> None:
        """Thread-safe async initialization of client and collection."""
        if self._collection_ready:
            return
        async with self._init_lock:
            if self._collection_ready:
                return
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ensure_collection)

    async def upsert(self, items: list[RagItem]) -> None:
        await self._init()
        loop = asyncio.get_running_loop()
        client = self._client

        data = []
        for item in items:
            row: dict[str, Any] = {
                "product_id": item.product_id,
                "category": item.category,
                "style": item.style,
                "color": item.color,
                "material": item.material,
                "image_url": item.image_url,
                "text_vector": item.text_embedding or [0.0] * self.text_dim,
                "image_vector": item.image_embedding or [0.0] * self.image_dim,
            }
            if item.sparse_embedding:
                row["sparse_vector"] = item.sparse_embedding
            data.append(row)

        await loop.run_in_executor(None, lambda: client.upsert(collection_name=self.collection, data=data))

    async def hybrid_search(
        self,
        image_path: str | None,
        text: str,
        category: str,
        top_k: int = 5,
        query_dense: list[float] | None = None,
        query_sparse: dict[int, float] | None = None,
        query_image: list[float] | None = None,
    ) -> list[RagResult]:
        await self._init()
        loop = asyncio.get_running_loop()
        client = self._client

        filter_expr = _build_category_filter(category)
        reqs = []

        # Text dense vector search
        if query_dense is not None:
            reqs.append(AnnSearchRequest(
                data=[query_dense],
                anns_field="text_vector",
                param={"metric_type": "COSINE"},
                limit=20,
                expr=filter_expr,
            ))

        # Sparse text search
        if query_sparse is not None:
            reqs.append(AnnSearchRequest(
                data=[query_sparse],
                anns_field="sparse_vector",
                param={"metric_type": "IP"},
                limit=20,
                expr=filter_expr,
            ))

        # Image vector search
        if query_image is not None:
            reqs.append(AnnSearchRequest(
                data=[query_image],
                anns_field="image_vector",
                param={"metric_type": "COSINE"},
                limit=20,
                expr=filter_expr,
            ))

        if reqs:
            results = await loop.run_in_executor(
                None,
                lambda: client.hybrid_search(
                    collection_name=self.collection,
                    reqs=reqs,
                    ranker=RRFRanker(k=60),
                    limit=top_k,
                    output_fields=["product_id", "image_url", "style", "color", "material"],
                ),
            )
            out = []
            for hits in results:
                for hit in hits:
                    entity = hit.get("entity", {})
                    out.append(RagResult(
                        product_id=entity.get("product_id", ""),
                        score=hit.get("distance", 0.0),
                        image_url=entity.get("image_url", ""),
                        metadata={k: v for k, v in entity.items() if k not in {"product_id", "image_url"}},
                    ))
            return out

        return []

    async def health(self) -> dict:
        client = self._ensure_client()
        if not client.has_collection(self.collection):
            return {"status": "ok", "backend": "milvus", "count": 0}
        stats = client.get_collection_stats(self.collection)
        return {"status": "ok", "backend": "milvus", "count": stats.get("row_count", 0)}
