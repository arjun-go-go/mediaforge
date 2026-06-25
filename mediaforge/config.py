from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    database_url: str = "postgresql+asyncpg://mediaforge:mediaforge@localhost/mediaforge"
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional HTTP(S) proxy for outbound calls to model providers. Empty =
    # no explicit proxy; langchain-openai / httpx will fall back to the
    # process' HTTP_PROXY / HTTPS_PROXY env vars if set.
    http_proxy: str = ""
    jwt_secret: str = ""
    output_dir: str = "./outputs"
    upload_dir: str = "./uploads"
    max_upload_size: int = 50 * 1024 * 1024
    upload_url_prefix: str = "/uploads"

    # Object storage: "local" writes to output_dir (dev default),
    # "s3" uploads to S3/MinIO/OSS via the same protocol.
    storage_backend: str = "local"
    s3_endpoint_url: str = ""          # empty = AWS default; MinIO e.g. "http://minio:9000"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_public_base_url: str = ""       # empty = derived from endpoint+bucket
    s3_force_path_style: bool = True   # MinIO requires True; AWS can be False

    default_image_model: str = "pro"
    default_video_model: str = "veo"

    # Image model API names (alias → full model string)
    image_model_pro: str = "google/gemini-3-pro-image"
    image_model_fast: str = "openai/gpt-5.4-image-2"

    # Video model API names (alias → full model string)
    video_model_veo: str = "google/veo-3.1"
    video_model_seedance: str = "bytedance/seedance-2.0"

    # Semaphore limits (global across tenants)
    semaphore_gemini_pro_image: int = 10
    semaphore_gpt_image: int = 15
    semaphore_veo: int = 5
    semaphore_seedance: int = 8

    # LangSmith observability
    langsmith_api_key: str | None = None
    langsmith_project: str = "mediaforge"
    langsmith_tracing_v2: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # Vector store
    vector_store_backend: str = "chroma"
    chroma_persist_dir: str = "./chroma"
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""             # Zilliz Cloud API key (empty for self-hosted)
    milvus_db_name: str = "default"
    milvus_collection: str = "mediaforge"

    # DashScope embedding models
    dashscope_text_model: str = "text-embedding-v4"
    dashscope_text_dim: int = 1024
    dashscope_image_model: str = "qwen3-vl-embedding"
    dashscope_image_dim: int = 2560
    dashscope_rerank_model: str = "qwen3-vl-rerank"
    dashscope_api_key: str = ""

    # Site metadata (used in OpenRouter HTTP-Referer and X-Title headers)
    site_url: str = "https://mediaforge.local"
    site_title: str = "MediaForge"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_expires_seconds: int = 30 * 60          # 30 min
    jwt_refresh_secret: str = ""                        # separate secret for refresh tokens
    jwt_refresh_expires_seconds: int = 7 * 24 * 3600   # 7 days

    # Cookies
    cookie_access_name: str = "mf_access"
    cookie_refresh_name: str = "mf_refresh"
    cookie_csrf_name: str = "mf_csrf"
    cookie_secure: bool = False                         # set True in production (HTTPS)
    cookie_same_site: str = "Lax"                       # "Lax" | "Strict" | "None"
    cookie_domain: str = ""                             # empty = current host

    # CSRF
    csrf_header_name: str = "X-CSRF-Token"

    # Password
    password_min_length: int = 8
    password_bcrypt_rounds: int = 12

    # Login rate limit
    login_max_attempts: int = 5
    login_lockout_seconds: int = 15 * 60

    # Signup control: empty = self-signup disabled; set to a tenant_id to allow
    allow_self_signup_tenant_id: str = ""

    # CORS origins (comma-separated). Frontend dev origin included by default.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Dev: allow legacy X-Api-Key → hardcoded DEMO_KEY_* env lookup.
    # Set BACKCOMPAT_DEMO_KEYS=true in .env for local dev only.
    backcompat_demo_keys: bool = False

    # Supervisor agent model
    agent_model: str = "openai/gpt-4o-mini"

    # Demo API keys (do NOT hardcode real keys; set in .env)
    demo_key_starter: str = "demo-key-starter"
    demo_key_pro: str = "demo-key-pro"
    demo_key_enterprise: str = "demo-key-enterprise"

    # Celery
    celery_concurrency: int = 4          # parallel job workers
    celery_max_retries: int = 3
    celery_retry_backoff: int = 60       # seconds, doubles each retry

    # Logging (Loguru)
    log_level: str = "INFO"
    log_format: str = "console"       # "console" | "json"
    log_file: str = ""                # empty = no file, e.g. "./logs/mediaforge.log"
    log_rotation: str = "50 MB"
    log_retention: str = "30 days"
    log_compression: str = "zip"

    @model_validator(mode="after")
    def _defaults(self) -> "Settings":
        if not self.jwt_refresh_secret:
            self.jwt_refresh_secret = self.jwt_secret
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
