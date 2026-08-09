from abc import ABC, abstractmethod

from mediaforge.rag.models import RagItem, RagResult


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, items: list[RagItem]) -> None: ...

    @abstractmethod
    async def get_by_product_id(
        self, product_id: str, tenant_id: str = ""
    ) -> RagResult | None: ...

    @abstractmethod
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
    ) -> list[RagResult]: ...

    @abstractmethod
    async def health(self) -> dict: ...
