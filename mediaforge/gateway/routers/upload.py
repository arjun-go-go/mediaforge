import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_tenant_only
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.tenant import Tenant
from mediaforge.storage import get_storage

router = APIRouter(prefix="/api/v1")

CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}

CHUNK_SIZE = 1024 * 1024


class UploadResponse(BaseModel):
    url: str


@router.get("/files/{object_key:path}")
async def read_file(
    object_key: str,
    tenant: Tenant = Depends(get_tenant_only),
) -> Response:
    tenant_id = str(tenant.tenant_id)
    allowed_prefixes = (
        f"assets/{tenant_id}/",
        f"uploads/{tenant_id}/",
        f"rag/products/{tenant_id}/",
        "rag/products/global/",
    )
    if not object_key.startswith(allowed_prefixes):
        raise HTTPException(status_code=403, detail="File access denied")

    storage = get_storage()
    data = await storage.get_internal(object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(
        content=data,
        media_type=storage.content_type_for_key(object_key),
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("30/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant_only),
) -> UploadResponse:
    settings = get_settings()

    ct = (file.content_type or "").split(";")[0].strip().lower()
    ext = CONTENT_TYPE_TO_EXT.get(ct)
    if not ext:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_size:
                raise HTTPException(status_code=413, detail="Upload too large")
            chunks.append(chunk)
    finally:
        await file.close()

    upload_id = uuid.uuid4().hex
    try:
        url = await get_storage().save_upload(
            str(tenant.tenant_id), upload_id, b"".join(chunks), ext
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to store upload in MinIO") from exc
    return UploadResponse(url=url)
