import os
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
    app_env: str = "development"
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional proxy used only by OpenRouter clients. It is never exported as
    # HTTP_PROXY / HTTPS_PROXY, so MinIO and internal services are unaffected.
    http_proxy: str = ""
    jwt_secret: str = ""
    max_upload_size: int = 50 * 1024 * 1024

    # MinIO is the only asset storage backend.  The endpoint is used by the
    # API/worker; public_base_url is the browser-facing address.
    minio_endpoint_url: str = "http://localhost:9000"
    minio_bucket: str = "mediaforge"
    minio_region: str = "us-east-1"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_public_base_url: str = "/api/v1/files"
    minio_bypass_proxy: bool = True

    default_image_model: str = "pro"
    default_video_model: str = "veo"

    # Image model API names (alias → full model string)
    image_model_pro: str = "google/gemini-3.1-flash-image"
    image_model_fast: str = "openai/gpt-image-2"
    image_model_base: str = "qwen/qwen-image-3-pro"

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
    langsmith_tracing: bool = False
    langsmith_tracing_v2: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # Milvus / Zilliz Cloud is the only vector store backend.
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""  # Zilliz Cloud API key (empty for self-hosted)
    milvus_db_name: str = "default"
    milvus_collection: str = "mediaforge"

    # DashScope embedding models
    dashscope_text_model: str = "text-embedding-v4"
    dashscope_text_dim: int = 1024
    dashscope_image_model: str = "qwen3-vl-embedding"
    dashscope_image_dim: int = 2560
    dashscope_rerank_model: str = "qwen3-vl-rerank"
    dashscope_api_key: str = ""
    bestseller_min_sales_count: int = 1500
    bestseller_candidate_count: int = 12
    bestseller_style_reference_count: int = 3

    # Site metadata (used in OpenRouter HTTP-Referer and X-Title headers)
    site_url: str = "https://mediaforge.local"
    site_title: str = "MediaForge"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_expires_seconds: int = 30 * 60  # 30 min
    jwt_refresh_secret: str = ""  # separate secret for refresh tokens
    jwt_refresh_expires_seconds: int = 7 * 24 * 3600  # 7 days

    # Cookies
    cookie_access_name: str = "mf_access"
    cookie_refresh_name: str = "mf_refresh"
    cookie_csrf_name: str = "mf_csrf"
    cookie_secure: bool = False  # set True in production (HTTPS)
    cookie_same_site: str = "Lax"  # "Lax" | "Strict" | "None"
    cookie_domain: str = ""  # empty = current host

    # CSRF
    csrf_header_name: str = "X-CSRF-Token"

    # Password
    password_min_length: int = 8
    password_bcrypt_rounds: int = 12

    # Login rate limit
    login_max_attempts: int = 5
    login_lockout_seconds: int = 15 * 60

    # Public signup is disabled by default. Enable only for a controlled local demo.
    allow_self_signup: bool = False

    # CORS origins (comma-separated). Frontend dev origin included by default.
    cors_origins: str = "http://localhost:3100,http://127.0.0.1:3100"

    # Supervisor agent model
    agent_model: str = "openai/gpt-4o-mini"
    agent_fallback_model: str = "openai/gpt-4o-mini"
    quality_model: str = "openai/gpt-4o-mini"
    agent_concurrency_per_tenant: int = 2
    agent_confirmation_ttl_seconds: int = 15 * 60
    agent_graph_cache_size: int = 256
    agent_recursion_limit: int = 12
    agent_max_output_tokens: int = 1200
    agent_temperature: float = 0.0
    agent_rag_min_score: float = 0.25
    agent_prompt_version: str = "2026-08-07.8"
    agent_summary_trigger_messages: int = 30
    agent_summary_keep_messages: int = 12

    # Celery
    celery_concurrency: int = 4  # parallel job workers
    celery_max_retries: int = 3
    celery_retry_backoff: int = 60  # seconds, doubles each retry

    # Logging (Loguru)
    log_level: str = "INFO"
    log_format: str = "console"  # "console" | "json"
    log_file: str = ""  # empty = no file, e.g. "./logs/mediaforge.log"
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


def configure_langsmith_environment(settings: Settings | None = None) -> None:
    """Expose validated .env settings to the LangSmith SDK."""
    current = settings or get_settings()
    os.environ["LANGSMITH_TRACING"] = "true" if current.langsmith_tracing else "false"
    os.environ["LANGSMITH_PROJECT"] = current.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = current.langsmith_endpoint
    if current.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = current.langsmith_api_key


def clear_settings_cache() -> None:
    get_settings.cache_clear()
