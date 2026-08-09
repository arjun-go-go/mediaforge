from typing import Protocol, runtime_checkable

from loguru import logger

from mediaforge.rag.models import RagResult

MIN_RESULTS_THRESHOLD = 1


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
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
    ) -> list[RagResult]: ...


class ReferenceRetriever:
    """Multi-round retrieval with progressive filter relaxation.

    Accepts any object implementing the retrieve() protocol
    (CachedRetriever, or another ReferenceRetriever for nesting).
    """

    def __init__(self, backend: Retriever):
        self.backend = backend

    async def retrieve(
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
        # Round 1: exact category filter
        results = await self._search(
            image_path, text, category, tenant_id, top_k, query_dense, query_image,
            min_sales_count, quality_status,
        )
        if len(results) >= MIN_RESULTS_THRESHOLD:
            return results

        # Round 2: no category filter (broaden search)
        logger.info("Retrieval round 1 returned {} results, retrying without category filter", len(results))
        results = await self._search(
            image_path, text, None, tenant_id, top_k, query_dense, query_image,
            min_sales_count, quality_status,
        )
        if len(results) >= MIN_RESULTS_THRESHOLD:
            return results

        # Round 3: minimal filter — just return whatever we get
        logger.info("Retrieval round 2 returned {} results, final attempt with relaxed query", len(results))
        short_text = self._shorten_query(text)
        if short_text != text:
            results = await self._search(
                image_path, short_text, None, tenant_id, top_k, query_dense, query_image,
                min_sales_count, quality_status,
            )

        return results

    async def _search(
        self,
        image_path: str | None,
        text: str,
        category: str | None,
        tenant_id: str,
        top_k: int,
        query_dense: list[float] | None,
        query_image: list[float] | None = None,
        min_sales_count: int = 0,
        quality_status: str = "",
    ) -> list[RagResult]:
        return await self.backend.retrieve(
            image_path=image_path,
            text=text,
            category=category or "",
            tenant_id=tenant_id,
            top_k=top_k,
            query_dense=query_dense,
            query_image=query_image,
            min_sales_count=min_sales_count,
            quality_status=quality_status,
        )

    @staticmethod
    def _shorten_query(text: str) -> str:
        """Keep only the first two words to broaden the query."""
        parts = text.strip().split()
        return " ".join(parts[:2]) if len(parts) > 2 else text
