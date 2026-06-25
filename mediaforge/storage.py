"""Object storage abstraction.

Two backends:

* ``local`` — writes under ``settings.output_dir``, returns the relative path
  ``<tenant>/<job>/<asset>.<ext>``. The FastAPI app serves these under
  ``/outputs/`` via ``StaticFiles``. Default for development.

* ``s3``   — uploads to S3 / MinIO / OSS / R2 via ``aioboto3``. Returns the
  public URL (either ``s3_public_base_url`` or derived from endpoint+bucket).

Backend is selected by ``settings.storage_backend``. Callers should treat the
returned string as opaque — either a relative path the gateway will serve, or
an absolute URL pointing at object storage.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from mediaforge.config import Settings, get_settings


class Storage(Protocol):
    async def save_asset(
        self,
        tenant_id: str,
        job_id: str,
        asset_id: str,
        data: bytes,
        ext: str = "png",
    ) -> str: ...


class LocalStorage:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir).resolve()

    async def save_asset(
        self,
        tenant_id: str,
        job_id: str,
        asset_id: str,
        data: bytes,
        ext: str = "png",
    ) -> str:
        directory = self.base_dir / tenant_id / job_id
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        path = directory / f"{asset_id}.{ext}"
        await asyncio.to_thread(path.write_bytes, data)
        return f"{tenant_id}/{job_id}/{asset_id}.{ext}"


class S3Storage:
    """S3-compatible storage (AWS S3, MinIO, Cloudflare R2, Aliyun OSS via S3 API)."""

    def __init__(self, settings: Settings):
        if not settings.s3_bucket:
            raise ValueError("s3_bucket must be set when storage_backend=s3")
        self.bucket = settings.s3_bucket
        self.endpoint_url = settings.s3_endpoint_url or None
        self.region = settings.s3_region
        self.access_key = settings.s3_access_key
        self.secret_key = settings.s3_secret_key
        self.force_path_style = settings.s3_force_path_style
        self.public_base_url = settings.s3_public_base_url.rstrip("/")

    def _public_url(self, key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        if self.endpoint_url:
            base = self.endpoint_url.rstrip("/")
            if self.force_path_style:
                return f"{base}/{self.bucket}/{key}"
            return f"{base.replace('://', f'://{self.bucket}.', 1)}/{key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"

    @staticmethod
    def _content_type(ext: str) -> str:
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "mp4": "video/mp4",
            "webm": "video/webm",
        }.get(ext.lower(), "application/octet-stream")

    async def save_asset(
        self,
        tenant_id: str,
        job_id: str,
        asset_id: str,
        data: bytes,
        ext: str = "png",
    ) -> str:
        import aioboto3

        key = f"{tenant_id}/{job_id}/{asset_id}.{ext}"
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key or None,
            aws_secret_access_key=self.secret_key or None,
        ) as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=self._content_type(ext),
            )
        return self._public_url(key)


def get_storage(settings: Settings | None = None) -> Storage:
    s = settings or get_settings()
    if s.storage_backend == "s3":
        return S3Storage(s)
    return LocalStorage(s.output_dir)


# Backward-compat alias so existing imports keep working.
OutputStorage = LocalStorage
