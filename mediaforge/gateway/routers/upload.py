import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_tenant_only
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.models.tenant import Tenant

router = APIRouter(prefix="/api/v1")

CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}

CHUNK_SIZE = 8192


class UploadResponse(BaseModel):
    url: str


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

    upload_dir = Path(settings.upload_dir) / str(tenant.tenant_id)

    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Failed to save upload") from exc

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / filename
    saved_ok = False

    try:
        with dest.open("wb") as f:
            total = 0
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                if total + len(chunk) > settings.max_upload_size:
                    raise HTTPException(status_code=413, detail="Upload too large")
                total += len(chunk)
                await asyncio.to_thread(f.write, chunk)
        saved_ok = True
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Failed to save upload") from exc
    finally:
        if not saved_ok:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
        await file.close()

    url = f"{settings.upload_url_prefix.rstrip('/')}/{tenant.tenant_id}/{filename}"
    return UploadResponse(url=url)
