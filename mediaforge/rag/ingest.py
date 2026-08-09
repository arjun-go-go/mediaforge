"""Shared embedding + upsert logic for RAG data ingestion.

Used by both the FastAPI ingest endpoint and the offline seed script.
"""

import asyncio
import base64
import os
from pathlib import Path

from loguru import logger

from mediaforge.db.product_store import build_product_record, upsert_products
from mediaforge.rag.embeddings import DashScopeEmbeddingClient
from mediaforge.rag.factory import get_vector_store
from mediaforge.rag.models import RagItem
from mediaforge.storage import get_storage


def _build_search_text(row: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                str(row.get("category", "")),
                str(row.get("style", "")),
                str(row.get("color", "")),
                str(row.get("material", "")),
                str(row.get("season", "")),
                str(row.get("description", "")),
            ],
        )
    )


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


async def _prepare_image(
    row: dict,
    product_id: str,
    storage_scope: str,
    image_base_dir: str | None,
    image_files: dict[str, tuple[bytes, str]] | None,
) -> tuple[str, str]:
    """Return (embedding source, persisted MinIO URL)."""
    raw = str(row.get("image_url") or row.get("image_path") or "").strip()
    uploaded = (image_files or {}).get(Path(raw).name.lower()) if raw else None
    if uploaded:
        data, ext = uploaded
        minio_url = await get_storage().save_rag_product_image(
            scope=storage_scope,
            product_id=product_id,
            data=data,
            ext=ext,
        )
        clean_ext = ext.lower().lstrip(".")
        mime = "jpeg" if clean_ext in {"jpg", "jpeg"} else clean_ext
        source = f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
        return source, minio_url

    source = _resolve_image_url(row, image_base_dir)
    if not source:
        return "", ""
    if source.startswith(("http://", "https://", "data:")):
        return source, source

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        logger.warning("Image file not found for {}: {}", product_id, path)
        return "", ""

    data = await asyncio.to_thread(path.read_bytes)
    minio_url = await get_storage().save_rag_product_image(
        scope=storage_scope,
        product_id=product_id,
        data=data,
        ext=path.suffix or ".jpg",
    )
    return str(path), minio_url


async def embed_and_upsert(
    rows: list[dict],
    batch_size: int = 5,
    image_base_dir: str | None = None,
    image_files: dict[str, tuple[bytes, str]] | None = None,
    tenant_id: str | None = None,
    visibility: str | None = None,
    source_type: str | None = None,
    require_image: bool = False,
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
    visibility = visibility or ("private" if tenant_id else "global")
    source_type = source_type or ("user_upload" if tenant_id else "local_seed")
    storage_scope = tenant_id or "global"

    all_texts = [_build_search_text(r) for r in rows]
    document_ids = [f"{storage_scope}:{str(row['product_id']).strip()}" for row in rows]
    await upsert_products(
        [
            build_product_record(
                row,
                document_id=document_id,
                tenant_id=tenant_id,
                visibility=visibility,
                source_type=source_type,
                search_text=search_text,
            )
            for row, document_id, search_text in zip(rows, document_ids, all_texts)
        ]
    )

    items: list[RagItem] = []
    product_records: list[dict] = []
    total = len(rows)

    for start in range(0, total, batch_size):
        batch = rows[start : start + batch_size]
        texts = all_texts[start : start + batch_size]
        batch_document_ids = document_ids[start : start + batch_size]
        logger.info("Embedding batch {}–{} / {}", start + 1, min(start + batch_size, total), total)

        # Text embeddings — failures return None (row will be skipped)
        async def _safe_text_emb(text: str):
            try:
                return await embed_client.embed_text(text)
            except Exception as exc:
                logger.warning("Text embedding failed: {}", exc)
                return None

        text_embs = await asyncio.gather(*[_safe_text_emb(t) for t in texts])
        # Image embeddings — failures return None (image is optional)
        async def _safe_image_emb(url: str):
            if not url:
                return None
            try:
                return await embed_client.embed_image(url)
            except Exception as exc:
                logger.warning("Image embedding failed for {}: {}", url, exc)
                return None

        async def _safe_prepare_image(row: dict):
            try:
                source, url = await _prepare_image(
                    row,
                    str(row["product_id"]).strip(),
                    storage_scope,
                    image_base_dir,
                    image_files,
                )
                return source, url, None
            except Exception as exc:
                logger.warning("Image persistence failed for {}: {}", row.get("product_id"), exc)
                return "", "", str(exc)

        prepared_images = await asyncio.gather(
            *[
                _safe_prepare_image(row)
                for row in batch
            ]
        )
        image_sources = [source for source, _, _ in prepared_images]
        image_urls = [url for _, url, _ in prepared_images]
        image_errors = [error for _, _, error in prepared_images]
        image_embs = await asyncio.gather(*[_safe_image_emb(source) for source in image_sources])

        for row, document_id, search_text, text_emb, img_emb, img_url, image_error in zip(
            batch, batch_document_ids, texts, text_embs, image_embs, image_urls, image_errors
        ):
            errors: list[str] = []
            if require_image and not img_url:
                errors.append(image_error or "图片未成功保存到 MinIO")
            if require_image and img_emb is None:
                errors.append("图片向量生成失败")
            if require_image and text_emb is None:
                errors.append("文本向量生成失败")
            if not errors:
                items.append(
                    RagItem(
                        document_id=document_id,
                        product_id=str(row["product_id"]).strip(),
                        tenant_id=tenant_id or "",
                        visibility=visibility,
                        source_type=source_type,
                        category=str(row.get("category", "")).strip(),
                        style=str(row.get("style", "")).strip(),
                        color=str(row.get("color", "")).strip(),
                        material=str(row.get("material", "")).strip(),
                        season=str(row.get("season", "")).strip(),
                        sales_count=int(row.get("sales_count") or 0),
                        price=float(row["price"]) if row.get("price") not in (None, "") else None,
                        platform=str(row.get("platform", "")).strip(),
                        market=str(row.get("market", "")).strip(),
                        quality_status=str(row.get("quality_status") or "approved").strip(),
                        image_url=img_url,
                        search_text=search_text,
                        text_embedding=text_emb,
                        image_embedding=img_emb,
                    )
                )
            product_records.append(
                build_product_record(
                    row,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    visibility=visibility,
                    source_type=source_type,
                    search_text=search_text,
                    image_url=img_url,
                    index_status="failed" if errors else "indexed",
                    index_error="；".join(errors) or None,
                )
            )

        # Avoid rate limiting
        await asyncio.sleep(0.5)

        # Batch upsert to bound memory usage
        if len(product_records) >= batch_size * 2:
            if items:
                await vector_store.upsert(items)
            await upsert_products(product_records)
            logger.debug("RAG ingest: batch upserted {} items", len(items))
            items = []
            product_records = []

    if product_records:
        if items:
            await vector_store.upsert(items)
        await upsert_products(product_records)
    logger.info("RAG ingest complete: {} rows processed", len(rows))
    return len(rows)
