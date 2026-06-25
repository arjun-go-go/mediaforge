from abc import ABC, abstractmethod
from typing import Any

from chromadb.api.types import EmbeddingFunction

from mediaforge.rag.models import RagItem, RagResult


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, items: list[RagItem]) -> None: ...

    @abstractmethod
    async def hybrid_search(
        self,
        image_path: str | None,
        text: str,
        category: str,
        top_k: int = 5,
        query_dense: list[float] | None = None,
        query_sparse: dict[int, float] | None = None,
        query_image: list[float] | None = None,
    ) -> list[RagResult]: ...

    @abstractmethod
    async def health(self) -> dict: ...


class _SimpleEmbeddingFunction(EmbeddingFunction):
    """Deterministic, dependency-free embedding function for tests."""

    def __init__(self):
        pass

    def __call__(self, input: list[str]) -> list[list[float]]:
        import hashlib

        dim = 1024
        vectors: list[list[float]] = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((digest[i % len(digest)] / 255.0) * 2.0 - 1.0) for i in range(dim)]
            vectors.append(vec)
        return vectors

    @staticmethod
    def name() -> str:
        return "simple_hash"

    def get_config(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "_SimpleEmbeddingFunction":
        return _SimpleEmbeddingFunction()


class ChromaVectorStore(VectorStore):
    """Local testing backend using ChromaDB sqlite.

    Uses two collections: one for text embeddings, one for image embeddings.
    Hybrid search queries both and merges with RRF-style scoring.
    """

    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self._chroma = None
        self._text_col = None
        self._image_col = None

    def _ensure_client(self):
        if self._chroma is None:
            import chromadb

            self._chroma = chromadb.PersistentClient(path=self.persist_dir)
            self._text_col = self._chroma.get_or_create_collection(
                "mediaforge_text",
                embedding_function=_SimpleEmbeddingFunction(),
            )
            self._image_col = self._chroma.get_or_create_collection(
                "mediaforge_image",
                embedding_function=_SimpleEmbeddingFunction(),
            )

    async def upsert(self, items: list[RagItem]) -> None:
        import asyncio
        loop = asyncio.get_running_loop()
        self._ensure_client()

        meta_keys = {"text_embedding", "image_embedding", "sparse_embedding"}
        ids = [i.product_id for i in items]
        metadatas = [i.model_dump(exclude=meta_keys) for i in items]

        # Text collection
        text_embeddings = [i.text_embedding or [] for i in items]
        await loop.run_in_executor(
            None,
            lambda: self._text_col.upsert(
                ids=ids,
                embeddings=text_embeddings,
                metadatas=metadatas,
            ),
        )

        # Image collection — only rows with image_embedding
        img_ids, img_embs, img_metas = [], [], []
        for item, meta in zip(items, metadatas):
            if item.image_embedding:
                img_ids.append(item.product_id)
                img_embs.append(item.image_embedding)
                img_metas.append(meta)
        if img_ids:
            await loop.run_in_executor(
                None,
                lambda: self._image_col.upsert(
                    ids=img_ids,
                    embeddings=img_embs,
                    metadatas=img_metas,
                ),
            )

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
        import asyncio
        loop = asyncio.get_running_loop()
        self._ensure_client()

        rrf_k = 60
        scores: dict[str, float] = {}
        meta_map: dict[str, dict] = {}

        # Text search
        if query_dense is not None:
            results = await loop.run_in_executor(
                None,
                lambda: self._text_col.query(
                    query_embeddings=[query_dense],
                    n_results=top_k,
                    where={"category": category} if category else None,
                ),
            )
        else:
            results = await loop.run_in_executor(
                None,
                lambda: self._text_col.query(
                    query_texts=[text],
                    n_results=top_k,
                    where={"category": category} if category else None,
                ),
            )
        for rank, (pid, score, meta) in enumerate(
            zip(results["ids"][0], results["distances"][0], results["metadatas"][0]),
            start=1,
        ):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank)
            meta_map[pid] = meta

        # Image search
        if query_image is not None:
            try:
                img_results = await loop.run_in_executor(
                    None,
                    lambda: self._image_col.query(
                        query_embeddings=[query_image],
                        n_results=top_k,
                        where={"category": category} if category else None,
                    ),
                )
                for rank, (pid, score, meta) in enumerate(
                    zip(img_results["ids"][0], img_results["distances"][0], img_results["metadatas"][0]),
                    start=1,
                ):
                    scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank)
                    meta_map[pid] = meta
            except Exception:
                pass  # image collection may be empty

        # Sort by RRF score, descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RagResult(
                product_id=pid,
                score=score,
                image_url=meta_map.get(pid, {}).get("image_url", ""),
                metadata=meta_map.get(pid, {}),
            )
            for pid, score in ranked
        ]

    async def health(self) -> dict:
        import asyncio
        loop = asyncio.get_running_loop()
        self._ensure_client()
        text_count = await loop.run_in_executor(None, self._text_col.count)
        image_count = await loop.run_in_executor(None, self._image_col.count)
        return {"status": "ok", "backend": "chroma", "count": text_count, "image_count": image_count}
