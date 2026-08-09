import csv
import io
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_tenant_only
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.tenant import Tenant
from mediaforge.rag.embeddings import DashScopeEmbeddingClient
from mediaforge.rag.factory import get_vector_store
from mediaforge.rag.models import RagResult

router = APIRouter(prefix="/api/v1/rag")

REQUIRED_COLS = {"product_id", "category", "style", "color"}
ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


class IngestResponse(BaseModel):
    accepted: int
    message: str


class IngestStatusResponse(BaseModel):
    status: str
    count: int
    backend: str


class SearchRequest(BaseModel):
    query: str
    category: str = ""
    image_url: str = ""
    top_k: int = 5


class SearchResult(BaseModel):
    product_id: str
    score: float
    image_url: str
    metadata: dict


class SearchResponse(BaseModel):
    results: list[SearchResult]


def _parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV file is empty")
    missing = REQUIRED_COLS - set(rows[0].keys())
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return rows


def _parse_excel(content: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=422, detail="openpyxl not installed; use CSV format or install openpyxl"
        )
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    missing = REQUIRED_COLS - set(headers)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    rows = [dict(zip(headers, row)) for row in rows_iter if any(c is not None for c in row)]
    wb.close()
    return rows


def _rows_to_items(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    clean: list[dict] = []
    for row in rows:
        pid = str(row.get("product_id", "")).strip()
        if pid and pid not in seen:
            seen.add(pid)
            clean.append(row)
    return clean


async def _embed_and_upsert(
    rows: list[dict],
    tenant_id: str,
    image_files: dict[str, tuple[bytes, str]],
) -> None:
    from mediaforge.rag.ingest import embed_and_upsert

    await embed_and_upsert(
        rows,
        image_files=image_files,
        tenant_id=tenant_id,
        visibility="private",
        source_type="user_upload",
        require_image=True,
    )


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/minute")
async def ingest_products(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    images: list[UploadFile] = File(default=[]),
    tenant: Tenant = Depends(get_tenant_only),
) -> IngestResponse:
    settings = get_settings()

    ct = (file.content_type or "").split(";")[0].strip().lower()
    filename = (file.filename or "").lower()
    is_excel = filename.endswith((".xlsx", ".xls")) or ct in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    )
    is_csv = filename.endswith(".csv") or ct == "text/csv"

    if not is_excel and not is_csv and ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Only CSV and Excel files are supported")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        rows = _parse_excel(content) if is_excel else _parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = _rows_to_items(rows)
    if not rows:
        raise HTTPException(status_code=422, detail="No valid rows found after deduplication")

    image_files: dict[str, tuple[bytes, str]] = {}
    for image in images:
        filename = Path(image.filename or "").name
        if not filename:
            continue
        image_content = await image.read()
        ext = Path(filename).suffix or ".jpg"
        image_files[filename.lower()] = (image_content, ext)
        await image.close()

    missing_images: list[str] = []
    for row in rows:
        product_id = str(row.get("product_id") or "").strip()
        raw = str(row.get("image_url") or row.get("image_path") or "").strip()
        is_remote = raw.startswith(("http://", "https://", "data:"))
        is_uploaded = bool(raw) and Path(raw).name.lower() in image_files
        if not is_remote and not is_uploaded:
            missing_images.append(f"{product_id}: {raw or '未填写图片文件名'}")
    if missing_images:
        preview = "；".join(missing_images[:10])
        suffix = f"；另有 {len(missing_images) - 10} 条" if len(missing_images) > 10 else ""
        raise HTTPException(
            status_code=422,
            detail=f"以下商品没有匹配到上传图片：{preview}{suffix}",
        )

    background_tasks.add_task(
        _embed_and_upsert,
        rows,
        str(tenant.tenant_id),
        image_files,
    )

    return IngestResponse(
        accepted=len(rows),
        message=f"Accepted {len(rows)} products. Embedding and indexing in background.",
    )


@router.get("/status", response_model=IngestStatusResponse)
async def ingest_status(
    tenant: Tenant = Depends(get_tenant_only),
) -> IngestStatusResponse:
    vector_store = get_vector_store()
    health = await vector_store.health()
    return IngestStatusResponse(
        status=health.get("status", "unknown"),
        count=health.get("count", 0),
        backend=health.get("backend", "unknown"),
    )


@router.post("/search", response_model=SearchResponse)
async def search_products(
    body: SearchRequest,
    tenant: Tenant = Depends(get_tenant_only),
) -> SearchResponse:
    from mediaforge.rag.cached_retriever import CachedRetriever
    from mediaforge.rag.retriever import ReferenceRetriever

    embed_client = DashScopeEmbeddingClient()

    query_dense = None
    query_image = None

    try:
        query_dense = await embed_client.embed_text(body.query)
    except Exception as exc:
        logger.warning("Text dense embedding failed; BM25 search remains available: {}", exc)

    if body.image_url:
        try:
            query_image = await embed_client.embed_image(body.image_url)
        except Exception as exc:
            logger.warning("Embedding image failed: {}", exc)

    vector_store = get_vector_store()
    from mediaforge.db.redis_client import get_redis

    redis = await get_redis()
    cached = CachedRetriever(vector_store, redis=redis)
    retriever = ReferenceRetriever(cached)

    refs = await retriever.retrieve(
        image_path=body.image_url or None,
        text=body.query,
        category=body.category,
        tenant_id=str(tenant.tenant_id),
        top_k=body.top_k,
        query_dense=query_dense,
        query_image=query_image,
    )

    # Optional rerank
    if refs and len(refs) > 1:
        candidates = [
            {**r.metadata, "product_id": r.product_id, "image_url": r.image_url, "score": r.score}
            for r in refs
        ]
        try:
            reranked = await embed_client.rerank(
                query_text=body.query,
                query_image_path=body.image_url or None,
                candidates=candidates,
                top_n=body.top_k,
            )
            refs = [
                RagResult(
                    product_id=c["product_id"],
                    score=c.get("rerank_score", c.get("score", 0.0)),
                    image_url=c.get("image_url", ""),
                    metadata={
                        k: v
                        for k, v in c.items()
                        if k not in {"product_id", "image_url", "score", "rerank_score"}
                    },
                )
                for c in reranked
            ]
        except Exception as exc:
            logger.warning("Rerank failed: {}", exc)

    return SearchResponse(
        results=[
            SearchResult(
                product_id=r.product_id,
                score=r.score,
                image_url=r.image_url,
                metadata=r.metadata,
            )
            for r in refs
        ]
    )
