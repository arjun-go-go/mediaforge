"""Shared embedding + upsert logic for RAG data ingestion.

Used by both the FastAPI ingest endpoint and the offline seed script.
"""

import asyncio
import os
from pathlib import Path

from loguru import logger

from mediaforge.rag.embeddings import DashScopeEmbeddingClient
from mediaforge.rag.factory import get_vector_store
from mediaforge.rag.models import RagItem


def _build_tfidf_text(row: dict) -> str:
    return " ".join(filter(None, [
        str(row.get("category", "")),
        str(row.get("style", "")),
        str(row.get("color", "")),
        str(row.get("material", "")),
        str(row.get("description", "")),
    ]))


def _resolve_image_url(row: dict, image_base_dir: str | None = None) -> str:
    """Pick image location from row (image_url or image_path) and resolve relative paths."""
    raw = str(row.get("image_url") or row.get("image_path") or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://", "data:")) or Path(raw).is_absolute():
        return raw
    base = image_base_dir or os.environ.get("RAG_IMAGE_BASE_DIR", "")
    if base:
        return str(Path(base).expanduser().resolve() / raw)
    return raw


async def embed_and_upsert(
    rows: list[dict],
    batch_size: int = 5,
    image_base_dir: str | None = None,
) -> int:
    """Embed rows (text + optional image) and upsert into the vector store.

    Args:
        rows: List of row dicts from CSV/Excel.
        batch_size: Embedding batch size.
        image_base_dir: Optional base directory to resolve relative image paths against.
            Falls back to env var ``RAG_IMAGE_BASE_DIR`` when not provided.

    Returns the number of items upserted.
    """
    embed_client = DashScopeEmbeddingClient()
    vector_store = get_vector_store()

    # Build TF-IDF from all texts for sparse vectors
    all_texts = [_build_tfidf_text(r) for r in rows]
    embed_client.build_tfidf(all_texts)

    items: list[RagItem] = []
    total = len(rows)

    for start in range(0, total, batch_size):
        batch = rows[start : start + batch_size]
        texts = all_texts[start : start + batch_size]
        logger.info("Embedding batch {}–{} / {}", start + 1, min(start + batch_size, total), total)

        # Text embeddings — failures return None (row will be skipped)
        async def _safe_text_emb(text: str):
            try:
                return await embed_client.embed_text(text)
            except Exception as exc:
                logger.warning("Text embedding failed: {}", exc)
                return None

        text_embs = await asyncio.gather(*[_safe_text_emb(t) for t in texts])
        sparse_vecs = embed_client.encode_sparse_batch(texts)

        # Image embeddings — failures return None (image is optional)
        async def _safe_image_emb(url: str):
            if not url:
                return None
            try:
                return await embed_client.embed_image(url)
            except Exception as exc:
                logger.warning("Image embedding failed for {}: {}", url, exc)
                return None

        image_urls = [_resolve_image_url(r, image_base_dir) for r in batch]
        image_embs = await asyncio.gather(*[_safe_image_emb(u) for u in image_urls])

        for row, text_emb, sparse_vec, img_emb, img_url in zip(
            batch, text_embs, sparse_vecs, image_embs, image_urls
        ):
            if text_emb is None:
                logger.warning("Skipping row {} (text embedding failed)", row.get("product_id"))
                continue
            items.append(RagItem(
                product_id=str(row["product_id"]).strip(),
                category=str(row.get("category", "")).strip(),
                style=str(row.get("style", "")).strip(),
                color=str(row.get("color", "")).strip(),
                material=str(row.get("material", "")).strip(),
                image_url=img_url,
                text_embedding=text_emb,
                image_embedding=img_emb,
                sparse_embedding=sparse_vec or None,
            ))

        # Avoid rate limiting
        await asyncio.sleep(0.5)

        # Batch upsert to bound memory usage
        if len(items) >= batch_size * 2:
            await vector_store.upsert(items)
            logger.debug("RAG ingest: batch upserted {} items", len(items))
            items = []

    if items:
        await vector_store.upsert(items)
    logger.info("RAG ingest complete: {} rows processed", len(rows))
    return len(rows)
