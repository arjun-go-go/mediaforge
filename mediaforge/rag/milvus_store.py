import asyncio
import json
from typing import Any

from pymilvus import (
    AnnSearchRequest,
    DataType,
    Function,
    FunctionType,
    MilvusClient,
    RRFRanker,
)
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


def _build_search_filter(
    category: str | None,
    tenant_id: str | None,
    min_sales_count: int = 0,
    quality_status: str = "",
) -> str:
    scope_filter = 'visibility == "global"'
    if tenant_id:
        scope_filter = f'(visibility == "global" or tenant_id == "{tenant_id}")'
    filters = [scope_filter]
    category_filter = _build_category_filter(category)
    if category_filter:
        filters.append(category_filter)
    if min_sales_count > 0:
        filters.append(f"sales_count >= {int(min_sales_count)}")
    if quality_status and _CATEGORY_RE.match(quality_status):
        filters.append(f'quality_status == "{quality_status}"')
    return " and ".join(filters)



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
            schema.add_field("document_id", DataType.VARCHAR, max_length=160, is_primary=True)
            schema.add_field("product_id", DataType.VARCHAR, max_length=64)
            schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
            schema.add_field("visibility", DataType.VARCHAR, max_length=16)
            schema.add_field("source_type", DataType.VARCHAR, max_length=32)
            schema.add_field("category", DataType.VARCHAR, max_length=64)
            schema.add_field("style", DataType.VARCHAR, max_length=64)
            schema.add_field("color", DataType.VARCHAR, max_length=64)
            schema.add_field("material", DataType.VARCHAR, max_length=64)
            schema.add_field("season", DataType.VARCHAR, max_length=64)
            schema.add_field("sales_count", DataType.INT64)
            schema.add_field("price", DataType.FLOAT)
            schema.add_field("platform", DataType.VARCHAR, max_length=64)
            schema.add_field("market", DataType.VARCHAR, max_length=16)
            schema.add_field("quality_status", DataType.VARCHAR, max_length=20)
            schema.add_field("image_url", DataType.VARCHAR, max_length=512)
            schema.add_field(
                "search_text",
                DataType.VARCHAR,
                max_length=4096,
                enable_analyzer=True,
            )
            schema.add_field("text_vector", DataType.FLOAT_VECTOR, dim=self.text_dim)
            schema.add_field("image_vector", DataType.FLOAT_VECTOR, dim=self.image_dim)
            schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
            schema.add_function(
                Function(
                    name="search_text_bm25",
                    function_type=FunctionType.BM25,
                    input_field_names=["search_text"],
                    output_field_names=["sparse_vector"],
                )
            )

            index_params = client.prepare_index_params()
            index_params.add_index(field_name="text_vector", index_type="FLAT", metric_type="COSINE")
            index_params.add_index(field_name="image_vector", index_type="FLAT", metric_type="COSINE")
            index_params.add_index(
                field_name="sparse_vector",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="BM25",
            )

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
                "document_id": item.document_id,
                "product_id": item.product_id,
                "tenant_id": item.tenant_id,
                "visibility": item.visibility,
                "source_type": item.source_type,
                "category": item.category,
                "style": item.style,
                "color": item.color,
                "material": item.material,
                "season": item.season,
                "sales_count": item.sales_count,
                "price": item.price or 0.0,
                "platform": item.platform,
                "market": item.market,
                "quality_status": item.quality_status,
                "image_url": item.image_url,
                "search_text": item.search_text,
                "text_vector": item.text_embedding or [0.0] * self.text_dim,
                "image_vector": item.image_embedding or [0.0] * self.image_dim,
            }
            data.append(row)

        await loop.run_in_executor(None, lambda: client.upsert(collection_name=self.collection, data=data))

    async def get_by_product_id(
        self, product_id: str, tenant_id: str = ""
    ) -> RagResult | None:
        """Resolve an explicitly selected SKU with a scalar query, not BM25."""
        await self._init()
        loop = asyncio.get_running_loop()
        client = self._client
        product_literal = json.dumps(product_id)
        scope_filter = 'visibility == "global"'
        if tenant_id:
            scope_filter = (
                f'(visibility == "global" or tenant_id == {json.dumps(tenant_id)})'
            )
        rows = await loop.run_in_executor(
            None,
            lambda: client.query(
                collection_name=self.collection,
                filter=f"product_id == {product_literal} and {scope_filter}",
                output_fields=[
                    "document_id", "product_id", "tenant_id", "visibility",
                    "source_type", "category", "image_url", "style", "color",
                    "material", "season", "sales_count", "price", "platform",
                    "market", "quality_status", "search_text",
                ],
                limit=10,
            ),
        )
        if not rows:
            return None
        row = next(
            (item for item in rows if tenant_id and item.get("tenant_id") == tenant_id),
            rows[0],
        )
        metadata = {
            key: value
            for key, value in row.items()
            if key not in {"document_id", "product_id", "image_url"}
        }
        metadata["document_id"] = row.get("document_id", "")
        metadata["text"] = metadata.pop("search_text", "")
        return RagResult(
            product_id=row.get("product_id", ""),
            score=1.0,
            image_url=row.get("image_url", ""),
            metadata=metadata,
        )

    async def hybrid_search(
        self,
        image_path: str | None,
        text: str,
        category: str,
        tenant_id: str = "",
        top_k: int = 5,
        query_dense: list[float] | None = None,
        query_image: list[float] | None = None,
        min_sales_count: int = 0,
        quality_status: str = "",
    ) -> list[RagResult]:
        await self._init()
        loop = asyncio.get_running_loop()
        client = self._client

        filter_expr = _build_search_filter(
            category, tenant_id, min_sales_count, quality_status
        )
        reqs = []
        candidate_limit = max(20, top_k * 4)

        # Text dense vector search
        if query_dense is not None:
            reqs.append(AnnSearchRequest(
                data=[query_dense],
                anns_field="text_vector",
                param={"metric_type": "COSINE"},
                limit=candidate_limit,
                expr=filter_expr,
            ))

        # Raw text is analyzed by the collection's BM25 function.
        if text.strip():
            reqs.append(AnnSearchRequest(
                data=[text],
                anns_field="sparse_vector",
                param={"metric_type": "BM25"},
                limit=candidate_limit,
                expr=filter_expr,
            ))

        # Image vector search
        if query_image is not None:
            reqs.append(AnnSearchRequest(
                data=[query_image],
                anns_field="image_vector",
                param={"metric_type": "COSINE"},
                limit=candidate_limit,
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
                    output_fields=[
                        "document_id", "product_id", "tenant_id", "visibility",
                        "source_type", "category", "image_url", "style", "color",
                        "material", "season", "sales_count", "price", "platform",
                        "market", "quality_status", "search_text",
                    ],
                ),
            )
            out = []
            for hits in results:
                for hit in hits:
                    entity = hit.get("entity", {})
                    metadata = {
                        k: v
                        for k, v in entity.items()
                        if k not in {"document_id", "product_id", "image_url"}
                    }
                    metadata["document_id"] = entity.get("document_id", "")
                    metadata["text"] = metadata.pop("search_text", "")
                    out.append(RagResult(
                        product_id=entity.get("product_id", ""),
                        score=hit.get("distance", 0.0),
                        image_url=entity.get("image_url", ""),
                        metadata=metadata,
                    ))
            return out

        return []

    async def health(self) -> dict:
        client = self._ensure_client()
        if not client.has_collection(self.collection):
            return {"status": "ok", "backend": "milvus", "count": 0}
        rows = client.query(
            collection_name=self.collection,
            filter="",
            output_fields=["count(*)"],
        )
        count = int(rows[0].get("count(*)", 0)) if rows else 0
        return {"status": "ok", "backend": "milvus", "count": count}
