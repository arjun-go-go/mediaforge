import json
import re
import uuid
from typing import Any, Literal

from langchain_core.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from mediaforge.rag.embeddings import DashScopeEmbeddingClient
from mediaforge.rag.retriever import ReferenceRetriever
from mediaforge.rag.vector_store import VectorStore

RRF_FALLBACK_MIN_SCORE = 0.025

_CATEGORY_FAMILIES = {
    "top": ("t恤", "上衣", "衬衫", "针织", "毛衣", "背心", "tee", "shirt", "top", "blouse", "sweater", "cardigan", "tank"),
    "bottom": ("裤", "牛仔裤", "半身裙", "短裤", "pants", "trousers", "jeans", "skirt", "shorts", "culottes", "leggings"),
    "dress": ("连衣裙", "礼服", "dress", "gown"),
    "outerwear": ("夹克", "外套", "风衣", "大衣", "jacket", "coat", "hoodie", "blazer"),
}


def _category_family(text: str) -> str | None:
    normalized = text.lower().replace("_", " ").replace("-", " ")
    for family, terms in _CATEGORY_FAMILIES.items():
        if any(term.lower() in normalized for term in terms):
            return family
    return None

_GENERIC_SEARCH_QUERIES = {
    "爆款",
    "爆款商品",
    "相似爆款",
    "相似商品",
    "商品",
    "热门商品",
    "参考商品",
    "通过新品图查找相似爆款参考",
}


def is_actionable_search_query(query_text: str, image_path: str | None = None) -> bool:
    if image_path:
        return True
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", query_text.strip().lower())
    return bool(normalized and normalized not in _GENERIC_SEARCH_QUERIES)


class RAGSearchInput(BaseModel):
    query_text: str = Field(default="查找与当前新品相似的爆款参考", description="用于检索参考产品的文本查询")
    category: str = Field(default="apparel", description="产品类目，如 apparel、electronics、home")
    top_k: int = Field(default=3, ge=1, le=10, description="返回的最相似商品数量（1-10）")
    image_path: str | None = Field(default=None, description="可选的视觉检索图片 URL 或本地路径")


class ProductFamilyAudit(BaseModel):
    family: Literal["top", "bottom", "dress", "outerwear", "other"]


class RAGSearchTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "rag_search"
    description: str = (
        "仅在用户明确要求开始查找，并且已有商品图片或具体类目、颜色、风格、材质等条件时，"
        "在参考库检索相似商品。用户询问‘怎么检索’等使用方法时禁止调用此工具。"
    )
    args_schema: type[BaseModel] = RAGSearchInput
    retriever: Any = None
    embed_client: Any = None
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = "default"

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        redis=None,
        tenant_id: str = "",
        user_id: str = "",
        session_id: str = "default",
        **kwargs,
    ):
        super().__init__(tenant_id=tenant_id, user_id=user_id, session_id=session_id, **kwargs)
        if vector_store:
            from mediaforge.rag.cached_retriever import CachedRetriever

            cached = CachedRetriever(vector_store, redis=redis)
            self.retriever = ReferenceRetriever(cached)
            self.embed_client = DashScopeEmbeddingClient()

    @staticmethod
    async def _detect_image_family(image_path: str) -> str | None:
        try:
            from mediaforge.config import get_settings
            from mediaforge.workers.openrouter_client import OpenRouterClient

            encoded = await OpenRouterClient._encode_image(image_path, max_px=512)
            result = await OpenRouterClient().structured_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                            {
                                "type": "text",
                                "text": (
                                    "Classify the dominant sellable fashion product only. Return family=top for "
                                    "T-shirts/shirts/tops, bottom for pants/jeans/skirts, dress for one-piece dresses, "
                                    "outerwear for jackets/coats, otherwise other."
                                ),
                            },
                        ],
                    }
                ],
                schema=ProductFamilyAudit,
                model=get_settings().quality_model,
                max_tokens=120,
            )
            return None if result.family == "other" else result.family
        except Exception as exc:
            logger.warning("Unable to classify uploaded product family: {}", exc)
            return None

    async def _arun(
        self,
        query_text: str = "查找与当前新品相似的爆款参考",
        category: str = "apparel",
        top_k: int = 3,
        image_path: str | None = None,
    ) -> str:
        source_descriptor = ""
        if not image_path and self.tenant_id and self.user_id:
            from sqlalchemy import select

            from mediaforge.db.engine import get_engine
            from mediaforge.db.tables import AgentSessionTable

            table = AgentSessionTable.__table__
            async with get_engine().connect() as connection:
                context = (
                    await connection.execute(
                        select(table.c.context).where(
                            table.c.tenant_id == uuid.UUID(self.tenant_id),
                            table.c.user_id == uuid.UUID(self.user_id),
                            table.c.session_id == self.session_id,
                        )
                    )
                ).scalar_one_or_none() or {}
            active_source = context.get("active_source")
            uploaded = context.get("uploaded_product") or {}
            selected = context.get("selected_product") or {}
            source = uploaded if active_source == "uploaded_product" else selected
            if not source.get("image_url"):
                source = uploaded or selected
            image_path = source.get("image_url")
            source_descriptor = " ".join(
                str(source.get(key) or "")
                for key in ("image_name", "product_name", "category", "description")
            )
            if source.get("category") and category == "apparel":
                category = source["category"]

        if not is_actionable_search_query(query_text, image_path):
            return json.dumps(
                {
                    "ok": False,
                    "error_code": "SEARCH_CONTEXT_REQUIRED",
                    "message": "请先选择或上传商品，或者提供具体类目、风格、颜色、材质等检索条件",
                    "retryable": False,
                },
                ensure_ascii=False,
            )
        if self.retriever is None:
            return json.dumps(
                {
                    "ok": False,
                    "error_code": "RAG_NOT_CONFIGURED",
                    "message": "参考商品检索未配置",
                    "retryable": False,
                },
                ensure_ascii=False,
            )

        query_dense = None
        query_image = None

        if self.embed_client is not None:
            try:
                query_dense = await self.embed_client.embed_text(query_text)
            except Exception as exc:
                logger.warning("Text dense embedding failed; continuing with BM25 search: {}", exc)
            if image_path:
                try:
                    query_image = await self.embed_client.embed_image(image_path)
                except Exception as exc:
                    logger.warning(
                        "Image embedding failed, falling back to text-only search: {}", exc
                    )

        try:
            refs = await self.retriever.retrieve(
                image_path=image_path,
                text=query_text,
                category=category,
                tenant_id=self.tenant_id,
                top_k=max(top_k, 10),
                query_dense=query_dense,
                query_image=query_image,
            )
        except Exception as exc:
            logger.error("Agent RAG search failed: {}", exc)
            return json.dumps(
                {
                    "ok": False,
                    "error_code": "RAG_SEARCH_FAILED",
                    "message": "参考商品检索暂时不可用",
                    "retryable": True,
                },
                ensure_ascii=False,
            )
        requested_family = _category_family(
            f"{query_text} {category} {source_descriptor}"
        )
        if requested_family is None and image_path:
            requested_family = await self._detect_image_family(image_path)
        if requested_family:
            refs = [
                item
                for item in refs
                if _category_family(str(item.metadata.get("category") or ""))
                == requested_family
            ]

        from mediaforge.config import get_settings

        score_type = "rrf"
        used_rerank = False
        if refs and self.embed_client is not None:
            candidates = [
                {
                    **item.metadata,
                    "product_id": item.product_id,
                    "image_url": item.image_url,
                    "score": item.score,
                    "text": item.metadata.get("text", ""),
                }
                for item in refs
            ]
            reranked = await self.embed_client.rerank(
                query_text=query_text,
                query_image_path=image_path,
                candidates=candidates,
                top_n=top_k,
            )
            if any("rerank_score" in item for item in reranked):
                by_id = {item.product_id: item for item in refs}
                refs = [
                    by_id[item["product_id"]].model_copy(
                        update={"score": item["rerank_score"]}
                    )
                    for item in reranked
                    if item.get("product_id") in by_id
                ]
                score_type = "vl_rerank"
                used_rerank = True

        minimum_score = get_settings().agent_rag_min_score
        if self.embed_client is not None and not used_rerank:
            minimum_score = RRF_FALLBACK_MIN_SCORE
        logger.info(
            "Agent RAG candidates score_type={} threshold={} scores={}",
            score_type,
            minimum_score,
            [(item.product_id, round(item.score, 4)) for item in refs],
        )
        refs = [item for item in refs if item.score >= minimum_score]

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
            json.dumps(
                {
                    "ok": True,
                    "matched": True,
                    "minimum_score": minimum_score,
                    "score_type": score_type,
                    "results": results,
                },
                ensure_ascii=False,
            )
            if results
            else json.dumps(
                {
                    "ok": True,
                    "matched": False,
                    "message": "未找到达到可信阈值的参考商品，可继续使用无参考图生成",
                    "minimum_score": minimum_score,
                    "score_type": score_type,
                    "generation_fallback": "no_reference",
                },
                ensure_ascii=False,
            )
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async mode")
