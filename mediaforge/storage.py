"""MinIO-backed object storage.

Generated assets and user uploads share one MinIO bucket and are separated by
object-key prefixes.  No persistent application data is written to the local
filesystem.
"""

from __future__ import annotations

from functools import lru_cache

from mediaforge.config import Settings, get_settings


class MinioStorage:
    def __init__(self, settings: Settings):
        if not settings.minio_endpoint_url:
            raise ValueError("MINIO_ENDPOINT_URL must be configured")
        if not settings.minio_bucket:
            raise ValueError("MINIO_BUCKET must be configured")
        if not settings.minio_access_key or not settings.minio_secret_key:
            raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be configured")
        self.endpoint_url = settings.minio_endpoint_url.rstrip("/")
        self.bucket = settings.minio_bucket
        self.region = settings.minio_region
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key
        self.public_base_url = settings.minio_public_base_url.rstrip("/")
        self.bypass_proxy = settings.minio_bypass_proxy

    def _client(self):
        """Build an S3 client configured for MinIO-compatible direct access."""
        import aioboto3
        from botocore.config import Config

        config_kwargs = {
            "connect_timeout": 10,
            "read_timeout": 60,
            "retries": {"max_attempts": 3, "mode": "standard"},
            "request_checksum_calculation": "when_required",
            "response_checksum_validation": "when_required",
            "s3": {"addressing_style": "path"},
        }
        if self.bypass_proxy:
            config_kwargs["proxies"] = {}

        return aioboto3.Session().client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(**config_kwargs),
        )

    def _public_url(self, key: str) -> str:
        base = self.public_base_url or "/api/v1/files"
        return f"{base}/{key}"

    @classmethod
    def content_type_for_key(cls, key: str) -> str:
        return cls._content_type(key.rsplit(".", 1)[-1] if "." in key else "")

    @staticmethod
    def _content_type(ext: str) -> str:
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "mp4": "video/mp4",
            "mov": "video/quicktime",
            "webm": "video/webm",
        }.get(ext.lower().lstrip("."), "application/octet-stream")

    async def _put(self, key: str, data: bytes, ext: str) -> str:
        async with self._client() as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=self._content_type(ext),
            )
        return self._public_url(key)

    async def put_internal(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        async with self._client() as client:
            await client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )

    async def get_internal(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        async with self._client() as client:
            try:
                response = await client.get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                    return None
                raise
            async with response["Body"] as stream:
                return await stream.read()

    async def save_asset(
        self,
        tenant_id: str,
        job_id: str,
        asset_id: str,
        data: bytes,
        ext: str = "png",
    ) -> str:
        clean_ext = ext.lower().lstrip(".")
        key = f"assets/{tenant_id}/{job_id}/{asset_id}.{clean_ext}"
        return await self._put(key, data, clean_ext)

    async def save_upload(
        self,
        tenant_id: str,
        upload_id: str,
        data: bytes,
        ext: str,
    ) -> str:
        clean_ext = ext.lower().lstrip(".")
        key = f"uploads/{tenant_id}/{upload_id}.{clean_ext}"
        return await self._put(key, data, clean_ext)

    async def save_rag_product_image(
        self,
        scope: str,
        product_id: str,
        data: bytes,
        ext: str,
    ) -> str:
        clean_ext = ext.lower().lstrip(".")
        key = f"rag/products/{scope}/{product_id}.{clean_ext}"
        return await self._put(key, data, clean_ext)


@lru_cache(maxsize=1)
def _cached_storage() -> MinioStorage:
    return MinioStorage(get_settings())


def get_storage(settings: Settings | None = None) -> MinioStorage:
    return MinioStorage(settings) if settings is not None else _cached_storage()


def clear_storage_cache() -> None:
    _cached_storage.cache_clear()
