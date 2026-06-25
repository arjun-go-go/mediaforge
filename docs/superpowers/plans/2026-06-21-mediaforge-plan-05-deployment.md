# MediaForge Plan 05: Docker Compose Deployment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package MediaForge for production deployment on a single server or small cluster using Docker Compose, with persistent PostgreSQL/Redis, ChromaDB for local testing, Milvus for production vector search, and LangSmith observability.

**Architecture:** Multi-service Compose file: `gateway` (FastAPI + uvicorn), `worker` (same image, asyncio job consumer), `frontend` (Next.js static export + nginx), `postgres`, `redis`, `chroma` (dev), and `milvus` (prod). Environment variables include LangSmith, OpenRouter, and vector-store backend selection.

**Tech Stack:** Docker, Docker Compose v2, nginx, PostgreSQL, Redis, ChromaDB, Milvus Standalone.

**Prerequisite:** Plans 01-04 implemented.

---

## File Structure

```
mediaforge/
├── docker-compose.yml
├── docker-compose.milvus.yml   # production vector store overlay
├── Dockerfile.gateway
├── Dockerfile.worker
├── Dockerfile.frontend
├── nginx.conf
├── scripts/
│   └── entrypoint.sh
└── mediaforge/rag/milvus_store.py
```

---

## Task 1: Gateway Dockerfile

**Files:**
- Create: `mediaforge/Dockerfile.gateway`
- Test: Build locally

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# mediaforge/Dockerfile.gateway
FROM python:3.12-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY mediaforge ./mediaforge

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "mediaforge.gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

- [ ] **Step 2: Build**

```bash
cd mediaforge
docker build -f Dockerfile.gateway -t mediaforge:gateway .
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.gateway
git commit -m "chore: gateway dockerfile"
```

---

## Task 2: Worker Dockerfile + Entrypoint

**Files:**
- Create: `mediaforge/Dockerfile.worker`
- Create: `mediaforge/scripts/entrypoint.sh`
- Test: Build locally

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# mediaforge/Dockerfile.worker
FROM mediaforge:gateway AS base

CMD ["python", "-m", "mediaforge.orchestrator.worker"]
```

- [ ] **Step 2: Create worker entrypoint module**

```python
# mediaforge/mediaforge/orchestrator/worker.py
import asyncio
import json

from mediaforge.config import get_settings
from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.redis_client import get_redis
from mediaforge.orchestrator.batch_graph import build_batch_graph
from mediaforge.orchestrator.state import JobState


async def consume():
    engine = get_engine()
    redis = await get_redis()
    store = JobStore(engine, redis)
    graph = build_batch_graph()

    while True:
        _, raw = await redis.brpop("mediaforge:jobs", timeout=5)
        if raw is None:
            continue
        payload = json.loads(raw)
        job_id = payload["job_id"]
        tenant_id = payload["tenant_id"]
        await store.start_job(job_id)

        initial = JobState(
            job_id=job_id,
            tenant_id=tenant_id,
            skus=payload["skus"],
            total_sku_count=len(payload["skus"]),
            status="running",
        )
        await graph.ainvoke(initial)


if __name__ == "__main__":
    asyncio.run(consume())
```

- [ ] **Step 3: Update batch router to enqueue instead of fire-and-forget**

Modify `mediaforge/mediaforge/gateway/routers/batch.py`:

```python
import json
from mediaforge.db.redis_client import get_redis

@router.post("/submit")
async def submit_batch(...):
    ...
    redis = await get_redis()
    await redis.lpush(
        "mediaforge:jobs",
        json.dumps({
            "job_id": job_id,
            "tenant_id": tenant.tenant_id,
            "skus": [s.model_dump(mode="json") for s in payload.skus],
        }),
    )
    return {"job_id": job_id, "status": "pending"}
```

- [ ] **Step 4: Build**

```bash
docker build -f Dockerfile.worker -t mediaforge:worker .
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.worker mediaforge/orchestrator/worker.py mediaforge/gateway/routers/batch.py
git commit -m "feat: background worker consuming redis queue"
```

---

## Task 3: Frontend Dockerfile

**Files:**
- Create: `mediaforge/frontend/Dockerfile`
- Create: `mediaforge/frontend/nginx.conf`
- Test: Build locally

- [ ] **Step 1: Create frontend Dockerfile**

```dockerfile
# mediaforge/frontend/Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: Create nginx.conf**

```nginx
# mediaforge/frontend/nginx.conf
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri.html /index.html;
    }

    location /api/ {
        proxy_pass http://gateway:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

- [ ] **Step 3: Build**

```bash
cd mediaforge/frontend
docker build -t mediaforge:frontend .
```

- [ ] **Step 4: Commit**

```bash
git add mediaforge/frontend/Dockerfile mediaforge/frontend/nginx.conf
git commit -m "chore: frontend dockerfile and nginx config"
```

---

## Task 4: Docker Compose

**Files:**
- Create: `mediaforge/docker-compose.yml`
- Test: `docker compose up -d --build`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# mediaforge/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: mediaforge
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: mediaforge
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mediaforge"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redisdata:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  chroma:
    image: chromadb/chroma:0.5.0
    volumes:
      - chromadata:/chroma/chroma
    ports:
      - "8001:8000"
    environment:
      - IS_PERSISTENT=TRUE

  gateway:
    build:
      context: .
      dockerfile: Dockerfile.gateway
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://mediaforge:${POSTGRES_PASSWORD}@postgres/mediaforge
      REDIS_URL: redis://redis:6379/0
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      JWT_SECRET: ${JWT_SECRET}
      OUTPUT_DIR: /app/outputs
      VECTOR_STORE_BACKEND: chroma
      CHROMA_PERSIST_DIR: /app/chroma
      LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}
      LANGSMITH_PROJECT: ${LANGSMITH_PROJECT:-mediaforge}
      LANGSMITH_TRACING_V2: "true"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      chroma:
        condition: service_started
    volumes:
      - outputs:/app/outputs
      - chromadata:/app/chroma

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    deploy:
      replicas: 4
    environment:
      DATABASE_URL: postgresql+asyncpg://mediaforge:${POSTGRES_PASSWORD}@postgres/mediaforge
      REDIS_URL: redis://redis:6379/0
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      OUTPUT_DIR: /app/outputs
      VECTOR_STORE_BACKEND: chroma
      CHROMA_PERSIST_DIR: /app/chroma
      LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}
      LANGSMITH_PROJECT: ${LANGSMITH_PROJECT:-mediaforge}
      LANGSMITH_TRACING_V2: "true"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      chroma:
        condition: service_started
    volumes:
      - outputs:/app/outputs
      - chromadata:/app/chroma

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - gateway

volumes:
  pgdata:
  redisdata:
  outputs:
  chromadata:
```

- [ ] **Step 2: Start stack**

```bash
cd mediaforge
docker compose up -d --build
```

- [ ] **Step 3: Health check**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: docker compose production stack with chroma and langsmith"
```

---

## Task 5: Database Migrations on Startup

**Files:**
- Create: `mediaforge/scripts/init_db.py`
- Modify: `mediaforge/Dockerfile.gateway` and `mediaforge/Dockerfile.worker`

- [ ] **Step 1: Create init_db.py**

```python
# mediaforge/scripts/init_db.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from mediaforge.db.tables import Base
from mediaforge.config import get_settings


async def main():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Update gateway entrypoint**

```dockerfile
CMD ["sh", "-c", "python scripts/init_db.py && uvicorn mediaforge.gateway.main:app --host 0.0.0.0 --port 8000 --workers 4"]
```

- [ ] **Step 3: Commit**

```bash
git add scripts/init_db.py Dockerfile.gateway Dockerfile.worker
git commit -m "chore: auto-create tables on startup"
```

---

## Task 6: Milvus Production VectorStore Backend

**Files:**
- Create: `mediaforge/mediaforge/rag/milvus_store.py`
- Modify: `mediaforge/mediaforge/config.py`
- Modify: `mediaforge/mediaforge/orchestrator/agent_graph.py`
- Test: `mediaforge/tests/test_milvus_store.py`

- [ ] **Step 1: Write failing test**

```python
# mediaforge/tests/test_milvus_store.py
import pytest
from unittest.mock import MagicMock, patch
from mediaforge.rag.milvus_store import MilvusVectorStore
from mediaforge.rag.models import RagItem


@pytest.mark.asyncio
async def test_milvus_upsert_and_search():
    with patch("mediaforge.rag.milvus_store.MilvusClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.search.return_value = [[{"entity": {"product_id": "P001", "image_url": "https://example.com/p001.jpg"}, "distance": 0.9}]]

        store = MilvusVectorStore(uri="http://localhost:19530", collection="mediaforge")
        await store.upsert([
            RagItem(
                product_id="P001",
                category="apparel",
                style="elegant",
                color="red",
                material="silk",
                image_url="https://example.com/p001.jpg",
                text_embedding=[0.1] * 1024,
            )
        ])
        results = await store.hybrid_search(None, "elegant silk dress", "apparel", top_k=3)
        assert len(results) == 1
        assert results[0].product_id == "P001"
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_milvus_store.py -v
```

- [ ] **Step 3: Implement MilvusVectorStore**

```python
# mediaforge/mediaforge/rag/milvus_store.py
import asyncio
from typing import Any

from pymilvus import MilvusClient

from mediaforge.rag.models import RagItem, RagResult
from mediaforge.rag.vector_store import VectorStore


class MilvusVectorStore(VectorStore):
    def __init__(self, uri: str, collection: str = "mediaforge", dim: int = 1024):
        self.uri = uri
        self.collection = collection
        self.dim = dim
        self._client = None

    def _ensure_client(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(uri=self.uri)
            if not self._client.has_collection(self.collection):
                self._client.create_collection(
                    collection_name=self.collection,
                    dimension=self.dim,
                    auto_id=False,
                    id_type="string",
                )
        return self._client

    async def upsert(self, items: list[RagItem]) -> None:
        loop = asyncio.get_event_loop()
        client = self._ensure_client()
        data = [
            {
                "id": item.product_id,
                "vector": item.text_embedding or [0.0] * self.dim,
                **item.model_dump(exclude={"text_embedding", "sparse_embedding", "product_id"}),
            }
            for item in items
        ]
        await loop.run_in_executor(None, lambda: client.upsert(collection_name=self.collection, data=data))

    async def hybrid_search(
        self,
        image_path: str | None,
        text: str,
        category: str,
        top_k: int = 5,
    ) -> list[RagResult]:
        loop = asyncio.get_event_loop()
        client = self._ensure_client()
        results = await loop.run_in_executor(
            None,
            lambda: client.search(
                collection_name=self.collection,
                data=[text],
                filter=f'category == "{category}"',
                limit=top_k,
                output_fields=["product_id", "image_url", "style", "color", "material"],
            ),
        )
        out = []
        for hits in results:
            for hit in hits:
                entity = hit.get("entity", {})
                out.append(
                    RagResult(
                        product_id=entity.get("product_id", ""),
                        score=hit.get("distance", 0.0),
                        image_url=entity.get("image_url", ""),
                        metadata={k: v for k, v in entity.items() if k not in {"product_id", "image_url"}},
                    )
                )
        return out

    async def health(self) -> dict:
        client = self._ensure_client()
        stats = client.get_collection_stats(self.collection)
        return {"status": "ok", "backend": "milvus", "count": stats.get("row_count", 0)}
```

- [ ] **Step 4: Add Milvus config and factory**

Modify `mediaforge/mediaforge/config.py`:

```python
    vector_store_backend: str = "chroma"
    chroma_persist_dir: str = "./chroma"
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "mediaforge"
```

Create `mediaforge/mediaforge/rag/factory.py`:

```python
# mediaforge/mediaforge/rag/factory.py
from mediaforge.config import get_settings
from mediaforge.rag.vector_store import VectorStore
from mediaforge.rag.milvus_store import MilvusVectorStore
from mediaforge.rag.vector_store import ChromaVectorStore


def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_store_backend == "milvus":
        return MilvusVectorStore(uri=settings.milvus_uri, collection=settings.milvus_collection)
    return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
```

- [ ] **Step 5: Update agent_graph to use factory**

Modify `mediaforge/mediaforge/orchestrator/agent_graph.py`:

```python
from mediaforge.rag.factory import get_vector_store

    vector_store = get_vector_store()
```

- [ ] **Step 6: Add pymilvus dependency**

```toml
"pymilvus>=2.4.0",
```

- [ ] **Step 7: Run tests, expect pass**

```bash
pytest tests/test_milvus_store.py -v
```

Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add mediaforge/rag/milvus_store.py mediaforge/rag/factory.py mediaforge/config.py mediaforge/orchestrator/agent_graph.py tests/test_milvus_store.py pyproject.toml
git commit -m "feat: Milvus production vector store backend"
```

---

## Task 7: Milvus Production Compose Overlay

**Files:**
- Create: `mediaforge/docker-compose.milvus.yml`

- [ ] **Step 1: Create overlay file**

```yaml
# mediaforge/docker-compose.milvus.yml
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
    volumes:
      - etcd:/etcd
    command: etcd -advertise-client-urls http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - minio:/minio_data
    command: minio server /minio_data

  milvus-standalone:
    image: milvusdb/milvus:v2.4.1
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - milvus:/var/lib/milvus
    ports:
      - "19530:19530"
    depends_on:
      - etcd
      - minio

  gateway:
    environment:
      VECTOR_STORE_BACKEND: milvus
      MILVUS_URI: http://milvus-standalone:19530
    depends_on:
      - milvus-standalone

  worker:
    environment:
      VECTOR_STORE_BACKEND: milvus
      MILVUS_URI: http://milvus-standalone:19530
    depends_on:
      - milvus-standalone

volumes:
  etcd:
  minio:
  milvus:
```

- [ ] **Step 2: Document usage**

```bash
cd mediaforge
docker compose -f docker-compose.yml -f docker-compose.milvus.yml up -d --build
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.milvus.yml
git commit -m "chore: Milvus production compose overlay"
```

---

## Plan 05 Acceptance Criteria

- `docker compose up -d --build` brings up all services including ChromaDB.
- `curl http://localhost:8000/health` returns OK.
- Worker replicas consume jobs from Redis `mediaforge:jobs`.
- PostgreSQL tables are auto-created on first startup.
- Frontend served on port 3000 proxies `/api/*` to gateway.
- `MilvusVectorStore` implements the `VectorStore` interface for production.
- `docker compose -f docker-compose.yml -f docker-compose.milvus.yml up -d` switches backend to Milvus.
- LangSmith environment variables are injected into gateway and worker containers.
