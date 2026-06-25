import json
from typing import Any

from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from mediaforge.rag.embeddings import DashScopeEmbeddingClient
from mediaforge.rag.retriever import ReferenceRetriever
from mediaforge.rag.vector_store import VectorStore



class RAGSearchInput(BaseModel):
    query_text: str = Field(description="用于检索参考产品的文本查询")
    category: str = Field(default="apparel", description="产品类目，如 apparel、electronics、home")
    top_k: int = Field(default=3, ge=1, le=10, description="返回的最相似商品数量（1-10）")
    image_path: str | None = Field(default=None, description="可选的视觉检索图片 URL 或本地路径")


class RAGSearchTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "rag_search"
    description: str = "在产品参考库中检索相似商品，返回匹配商品的评分、图片 URL、类目、风格、颜色、材质等信息。"
    args_schema: type[BaseModel] = RAGSearchInput
    retriever: Any = None
    embed_client: Any = None

    def __init__(self, vector_store: VectorStore | None = None, redis=None, **kwargs):
        super().__init__(**kwargs)
        if vector_store:
            from mediaforge.rag.cached_retriever import CachedRetriever
            cached = CachedRetriever(vector_store, redis=redis)
            self.retriever = ReferenceRetriever(cached)
            self.embed_client = DashScopeEmbeddingClient()

    async def _arun(self, query_text: str, category: str = "apparel", top_k: int = 3, image_path: str | None = None) -> str:
        if self.retriever is None:
            return json.dumps({"error": "RAG 未配置"}, ensure_ascii=False)

        query_dense = None
        query_sparse = None
        query_image = None

        if self.embed_client is not None:
            try:
                query_dense = await self.embed_client.embed_text(query_text)
                query_sparse = self.embed_client.encode_sparse(query_text)
            except Exception as exc:
                logger.error("Text embedding failed, cannot perform RAG search: {}", exc)
                return json.dumps({"error": f"文本向量化失败: {exc}"}, ensure_ascii=False)
            if image_path:
                try:
                    query_image = await self.embed_client.embed_image(image_path)
                except Exception as exc:
                    logger.warning("Image embedding failed, falling back to text-only search: {}", exc)

        refs = await self.retriever.retrieve(
            image_path=image_path,
            text=query_text,
            category=category,
            top_k=top_k,
            query_dense=query_dense,
            query_sparse=query_sparse,
            query_image=query_image,
        )

        results = [
            {
                "product_id": r.product_id,
                "score": round(r.score, 4),
                "image_url": r.image_url,
                "category": r.metadata.get("category", ""),
                "style": r.metadata.get("style", ""),
                "color": r.metadata.get("color", ""),
                "material": r.metadata.get("material", ""),
            }
            for r in refs
        ]
        return (
            json.dumps(results, ensure_ascii=False)
            if results
            else json.dumps({"message": "未找到相关参考商品"}, ensure_ascii=False)
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")
