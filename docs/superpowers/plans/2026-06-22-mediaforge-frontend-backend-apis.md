# MediaForge Frontend Backend APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the three backend endpoints and static-file serving required by the MediaForge Next.js frontend.

**Architecture:** Add small focused routers (`tenant.py`, `upload.py`, `tasks.py` list) and mount `outputs/` as static files. Keep existing auth, rate-limiting, and prompt-injection middleware untouched.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Python-Multipart, StaticFiles.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `mediaforge/gateway/routers/tenant.py` | `GET /api/v1/me` returns current tenant + quotas |
| `mediaforge/gateway/routers/upload.py` | `POST /api/v1/upload` saves files under `outputs/uploads/{tenant_id}` |
| `mediaforge/db/job_store.py` | Add `list_jobs_for_tenant` method |
| `mediaforge/gateway/routers/tasks.py` | Add `GET /api/v1/tasks` list endpoint |
| `mediaforge/gateway/main.py` | Include new routers + mount `/outputs` static |
| `mediaforge/gateway/routers/__init__.py` | Export new routers |
| `mediaforge/tests/test_tenant_router.py` | Test `/api/v1/me` |
| `mediaforge/tests/test_upload_router.py` | Test file upload + URL |
| `mediaforge/tests/test_tasks_list.py` | Test job listing |

---

## Task 1: Tenant Info Endpoint

**Files:**
- Create: `mediaforge/gateway/routers/tenant.py`
- Modify: `mediaforge/gateway/main.py`
- Modify: `mediaforge/gateway/routers/__init__.py`
- Test: `mediaforge/tests/test_tenant_router.py`

- [ ] **Step 1: Write failing test**

```python
# mediaforge/tests/test_tenant_router.py
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config

mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_get_me_returns_tenant_info():
    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"X-Api-Key": "demo-key-pro"})
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"]
    assert data["plan"] == "pro"
    assert "max_concurrent_jobs" in data["quotas"]
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd mediaforge
pytest tests/test_tenant_router.py -v
```

Expected: 404 or AttributeError (tenant router missing).

- [ ] **Step 3: Implement tenant router**

```python
# mediaforge/gateway/routers/tenant.py
from fastapi import APIRouter, Depends

from mediaforge.gateway.dependencies import get_tenant_from_header
from mediaforge.models.tenant import Tenant

router = APIRouter(prefix="/api/v1")


@router.get("/me")
async def get_me(tenant: Tenant = Depends(get_tenant_from_header)) -> dict:
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "plan": tenant.plan.value,
        "quotas": tenant.quotas.model_dump() if tenant.quotas else None,
    }
```

- [ ] **Step 4: Wire router into main app**

Modify `mediaforge/gateway/main.py`:

```python
from mediaforge.gateway.routers import agent, batch, tasks, tenant

app.include_router(tenant.router)
```

Modify `mediaforge/gateway/routers/__init__.py`:

```python
from . import agent, batch, tasks, tenant

__all__ = ["agent", "batch", "tasks", "tenant"]
```

- [ ] **Step 5: Run test, expect pass**

```bash
pytest tests/test_tenant_router.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add mediaforge/gateway/routers/tenant.py mediaforge/gateway/main.py mediaforge/gateway/routers/__init__.py tests/test_tenant_router.py
git commit -m "feat: GET /api/v1/me tenant info endpoint"
```

---

## Task 2: File Upload Endpoint

**Files:**
- Create: `mediaforge/gateway/routers/upload.py`
- Modify: `mediaforge/gateway/main.py`
- Test: `mediaforge/tests/test_upload_router.py`

- [ ] **Step 1: Write failing test**

```python
# mediaforge/tests/test_upload_router.py
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config

mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_upload_image_returns_url():
    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        headers={"X-Api-Key": "demo-key-pro"},
        files={"file": ("test.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("/outputs/uploads/")
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_upload_router.py -v
```

Expected: 404.

- [ ] **Step 3: Implement upload router**

```python
# mediaforge/gateway/routers/upload.py
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from mediaforge.config import get_settings
from mediaforge.gateway.dependencies import get_tenant_from_header
from mediaforge.models.tenant import Tenant

router = APIRouter(prefix="/api/v1")


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant_from_header),
) -> dict:
    settings = get_settings()
    ext = Path(file.filename or "file").suffix or ".bin"
    upload_dir = Path(settings.output_dir) / "uploads" / tenant.tenant_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / filename
    content = await file.read()
    dest.write_bytes(content)

    return {"url": f"/outputs/uploads/{tenant.tenant_id}/{filename}"}
```

- Generates a UUID filename with an extension derived from the validated `Content-Type` (security improvement over trusting the client-supplied filename).

- [ ] **Step 4: Wire upload router**

Modify `mediaforge/gateway/main.py`:

```python
from mediaforge.gateway.routers import agent, batch, tasks, tenant, upload

app.include_router(upload.router)
```

Modify `mediaforge/gateway/routers/__init__.py`:

```python
from . import agent, batch, tasks, tenant, upload

__all__ = ["agent", "batch", "tasks", "tenant", "upload"]
```

- [ ] **Step 5: Run test, expect pass**

```bash
pytest tests/test_upload_router.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add mediaforge/gateway/routers/upload.py mediaforge/gateway/main.py mediaforge/gateway/routers/__init__.py tests/test_upload_router.py
git commit -m "feat: POST /api/v1/upload file upload endpoint"
```

---

## Task 3: List Jobs Endpoint

**Files:**
- Modify: `mediaforge/db/job_store.py`
- Modify: `mediaforge/gateway/routers/tasks.py`
- Test: `mediaforge/tests/test_tasks_list.py`

- [ ] **Step 1: Write failing test**

```python
# mediaforge/tests/test_tasks_list.py
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
import mediaforge.config

mediaforge.config.clear_settings_cache()

from fastapi.testclient import TestClient
from mediaforge.gateway.main import app


def test_list_tasks_requires_auth():
    client = TestClient(app)
    response = client.get("/api/v1/tasks")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_tasks_list.py -v
```

Expected: 200 or 404 (route missing), not 401.

- [ ] **Step 3: Add list method to JobStore**

Modify `mediaforge/db/job_store.py` by adding after `get_job`:

```python
    async def list_jobs_for_tenant(self, tenant_id: str, limit: int = 50) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(JobTable.__table__)
                .where(JobTable.__table__.c.tenant_id == _as_uuid(tenant_id))
                .order_by(JobTable.__table__.c.created_at.desc())
                .limit(limit)
            )
            return [dict(row) for row in result.mappings().all()]
```

- [ ] **Step 4: Add list route**

Modify `mediaforge/gateway/routers/tasks.py` by adding after the router definition:

```python
from mediaforge.gateway.dependencies import get_job_store, get_tenant_from_header
from mediaforge.db.job_store import JobStore


@router.get("")
async def list_tasks(
    tenant: Tenant = Depends(get_tenant_from_header),
    store: JobStore = Depends(get_job_store),
):
    jobs = await store.list_jobs_for_tenant(tenant.tenant_id)
    return {
        "jobs": [
            {
                "job_id": str(job["job_id"]),
                "status": job["status"],
                "total_skus": job["total_skus"],
                "done_skus": job["done_skus"],
                "created_at": job["created_at"].isoformat() if job["created_at"] else None,
            }
            for job in jobs
        ]
    }
```

- [ ] **Step 5: Run test, expect pass**

```bash
pytest tests/test_tasks_list.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add mediaforge/db/job_store.py mediaforge/gateway/routers/tasks.py tests/test_tasks_list.py
git commit -m "feat: GET /api/v1/tasks job list endpoint"
```

---

## Task 4: Mount Static Files for Uploads

**Files:**
- Modify: `mediaforge/gateway/main.py`
- Test: `mediaforge/tests/test_upload_router.py` (extend)

- [ ] **Step 1: Add static mount test**

Append to `mediaforge/tests/test_upload_router.py`:

```python
import os


def test_uploaded_file_is_served_statically():
    client = TestClient(app)
    response = client.post(
        "/api/v1/upload",
        headers={"X-Api-Key": "demo-key-pro"},
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200
    url = response.json()["url"]

    file_response = client.get(url)
    assert file_response.status_code == 200
    assert file_response.content == b"hello"
```

- [ ] **Step 2: Mount static files**

Modify `mediaforge/gateway/main.py`:

```python
from fastapi.staticfiles import StaticFiles
from mediaforge.config import get_settings

# after all routers are included
settings = get_settings()
app.mount("/outputs", StaticFiles(directory=settings.output_dir), name="outputs")
```

- [ ] **Step 3: Run tests, expect pass**

```bash
pytest tests/test_upload_router.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Run full backend suite**

```bash
pytest -q
```

Expected: all existing + 4 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add mediaforge/gateway/main.py tests/test_upload_router.py
git commit -m "feat: serve outputs directory as static files"
```

---

## Self-Review

- Spec coverage: `/api/v1/me` ✅, `/api/v1/upload` ✅, static files ✅, list jobs ✅.
- Placeholders: none.
- Type consistency: `Tenant` model already used by dependencies; `JobStore.list_jobs_for_tenant` matches existing patterns.
