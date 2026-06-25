import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from mediaforge.config import get_settings
from mediaforge.gateway.middleware.csrf import CsrfMiddleware
from mediaforge.gateway.middleware.defense import PromptInjectionMiddleware
from mediaforge.gateway.middleware.observability import ObservabilityMiddleware
from mediaforge.gateway.middleware.rate_limit import limiter
from mediaforge.gateway.routers import agent, api_keys, auth, batch, models, rag, tasks, tenant, upload
from mediaforge.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
        log_rotation=settings.log_rotation,
        log_retention=settings.log_retention,
        log_compression=settings.log_compression,
    )
    logger.info(
        "MediaForge starting up (log_level={} backcompat_demo_keys={})",
        settings.log_level,
        settings.backcompat_demo_keys,
    )

    # Auto-seed RAG vector store if empty
    try:
        from mediaforge.rag.factory import get_vector_store
        vector_store = get_vector_store()
        health = await vector_store.health()
        if health.get("count", 0) == 0:
            default_csv = Path(__file__).resolve().parents[2] / "data" / "products.csv"
            if default_csv.exists():
                logger.info("RAG vector store is empty, auto-seeding from {}", default_csv)
                from mediaforge.rag.ingest import embed_and_upsert
                from mediaforge.gateway.routers.rag import _parse_csv, _rows_to_items
                content = await asyncio.to_thread(default_csv.read_bytes)
                rows = _parse_csv(content)
                rows = _rows_to_items(rows)
                if rows:
                    await embed_and_upsert(rows)
    except Exception as exc:
        logger.warning("Auto-seed RAG failed (non-fatal): {}", exc)

    yield

    # --- Shutdown: release all resources ---
    try:
        from mediaforge.orchestrator.agent_graph import close_checkpointer
        await close_checkpointer()
    except Exception:
        pass
    try:
        from mediaforge.db.engine import close_engine
        await close_engine()
    except Exception:
        pass
    try:
        from mediaforge.db.redis_client import close_redis
        await close_redis()
    except Exception:
        pass
    try:
        from mediaforge.http_clients import close_clients
        await close_clients()
    except Exception:
        pass
    await logger.complete()


settings = get_settings()

app = FastAPI(title="MediaForge", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware registration order matters: Starlette runs them in REVERSE order.
# Desired runtime chain (outer → inner): Observability → CORS → CSRF → Defense.
# So register: Defense, CSRF, CORS, Observability.
app.add_middleware(PromptInjectionMiddleware)
app.add_middleware(CsrfMiddleware)

cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)

# Routers
app.include_router(agent.router)
app.include_router(api_keys.router)
app.include_router(auth.router)
app.include_router(batch.router)
app.include_router(models.router)
app.include_router(tasks.router)
app.include_router(tenant.router)
app.include_router(upload.router)
app.include_router(rag.router)

output_path = Path(settings.output_dir)
output_path.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(output_path)), name="outputs")

upload_path = Path(settings.upload_dir)
upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")


@app.get("/health", tags=["ops"])
async def health():
    """Liveness probe — returns 200 as long as the process is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready():
    """Readiness probe — checks DB and Redis connectivity."""
    checks: dict[str, str] = {}
    ok = True

    # PostgreSQL
    try:
        from mediaforge.db.engine import get_engine
        async with get_engine().connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"
        ok = False

    # Redis
    try:
        from mediaforge.db.redis_client import get_redis
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        ok = False

    if not ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "degraded", "checks": checks})
    return {"status": "ok", "checks": checks}
