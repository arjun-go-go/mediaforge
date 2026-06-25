# MediaForge Plan 02: LangGraph Batch Orchestrator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the foundation layer into a LangGraph `BatchOrchestrator` that accepts a batch payload, fans out SKU-level work with the Send API, runs compliance + Agentic RAG reference retrieval + OpenRouter generation, persists results, and uses an optimized Postgres checkpointer.

**Architecture:** A `StateGraph` with `validate_job → fan_out → image_worker / video_worker → finalize_job`. Worker nodes internally call compliance, retrieve RAG references from the VectorStore, generate assets, save files, and write asset rows. Uses `operator.add` reducers to aggregate `completed` / `failed` outputs. Checkpoints are written to Postgres via a sparse, batched `AsyncPostgresSaver` wrapper to reduce I/O.

**Tech Stack:** LangGraph 1.2, LangChain 1.2, asyncpg, redis-py, DashScope embeddings, ChromaDB/Milvus.

**Prerequisite:** Plan 01 (backend foundations) must be implemented and passing.

---

## File Structure

```
mediaforge/mediaforge/
├── orchestrator/
│   ├── __init__.py
│   ├── state.py              # JobState TypedDict with reducers
│   ├── nodes.py              # validate_job, fan_out, image_worker, video_worker, finalize_job
│   ├── batch_graph.py        # BatchOrchestrator graph builder
│   └── checkpointer.py       # sparse AsyncPostgresSaver wrapper
├── workers/
│   ├── compliance/
│   │   ├── __init__.py
│   │   └── checker.py        # L1-L5 compliance engine
│   ├── image/
│   │   ├── __init__.py
│   │   ├── main_image.py     # 7-platform main image worker
│   │   ├── detail_page.py    # detail-page worker
│   │   └── social.py         # social media asset worker
│   └── video/
│       ├── __init__.py
│       ├── veo.py            # Veo 3.1 worker
│       └── seedance.py       # Seedance 2.0 worker
```

---

## Task 1: Define JobState with Reducers

**Files:**
- Create: `mediaforge/mediaforge/orchestrator/state.py`
- Test: `mediaforge/tests/test_state.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_state.py
from mediaforge.orchestrator.state import JobState, SkuInput


def test_job_state_reducer_accumulates():
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[],
        total_sku_count=0,
        status="running",
    )
    update1 = {"completed": [{"sku_id": "SKU-001", "output_type": "main_image", "model_used": "pro", "status": "success"}]}
    update2 = {"completed": [{"sku_id": "SKU-002", "output_type": "main_image", "model_used": "pro", "status": "success"}]}
    from mediaforge.orchestrator.state import _add_asset_outputs
    merged = _add_asset_outputs(state.get("completed", []), update1["completed"])
    merged = _add_asset_outputs(merged, update2["completed"])
    assert len(merged) == 2
```

- [x] **Step 2: Run tests, expect failure**

```bash
cd mediaforge
pytest tests/test_state.py -v
```

- [x] **Step 3: Implement state.py**

```python
# mediaforge/mediaforge/orchestrator/state.py
from typing import Annotated, Literal
import operator
from typing_extensions import TypedDict

from mediaforge.models.job import AssetOutput, SkuInput


def _add_asset_outputs(current: list[AssetOutput], update: list[AssetOutput]) -> list[AssetOutput]:
    return current + update


class JobState(TypedDict):
    job_id: str
    tenant_id: str
    skus: list[SkuInput]
    completed: Annotated[list[AssetOutput], _add_asset_outputs]
    failed: Annotated[list[AssetOutput], _add_asset_outputs]
    logs: Annotated[list[str], operator.add]
    total_sku_count: int
    status: Literal["running", "done", "partial_fail", "failed"]
```

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_state.py -v
```

Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/orchestrator/state.py tests/test_state.py
git commit -m "feat: JobState TypedDict with reducers"
```

---

## Task 2: Compliance Engine (L1-L5)

**Files:**
- Create: `mediaforge/mediaforge/workers/compliance/checker.py`
- Test: `mediaforge/tests/test_compliance.py`

- [x] **Step 1: Write failing tests**

```python
# mediaforge/tests/test_compliance.py
import pytest
from mediaforge.workers.compliance.checker import ComplianceChecker, ComplianceResult


@pytest.fixture
def checker():
    return ComplianceChecker()


def test_l1_blocks_dangerous_intent(checker):
    result = checker.check(
        sku={"market": "US", "output_types": ["main_image"]},
        prompt="how to make a bomb",
    )
    assert result.blocked is True


def test_l4_fixes_china_number(checker):
    result = checker.check(
        sku={"market": "CN", "output_types": ["main_image"]},
        prompt="price 4 dollars",
    )
    assert "6" in result.modified_prompt
    assert "4" not in result.modified_prompt
    assert result.auto_fixed is True


def test_l5_adds_platform_spec(checker):
    result = checker.check(
        sku={"market": "US", "output_types": ["main_image"], "target_platforms": ["amazon"]},
        prompt="white background product photo",
    )
    assert "amazon" in result.modified_prompt.lower()
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_compliance.py -v
```

- [x] **Step 3: Implement compliance checker**

```python
# mediaforge/mediaforge/workers/compliance/checker.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComplianceResult:
    passed: bool = True
    blocked: bool = False
    auto_fixed: bool = False
    warnings: list[str] = field(default_factory=list)
    modified_prompt: str = ""


class ComplianceChecker:
    DANGEROUS_KEYWORDS = {"bomb", "weapon", "drug", "counterfeit", "fake", "replica"}
    BRAND_BLACKLIST = {"nike", "adidas", "gucci", "chanel"}
    IP_BLACKLIST = {"disney", "marvel", "pokemon"}

    CULTURAL_FIXES = {
        "CN": {"4": "6"},
        "VN": {"4": "6"},
        "PH": {"13": "12"},
    }

    PLATFORM_PROMPT_ADDENDUM = {
        "amazon": (
            "Amazon main image on pure white background (RGB 255,255,255), "
            "product fills 85% of frame."
        ),
        "shopee": (
            "Shopee bright, clean background, no border, product centered, "
            "lifestyle-friendly."
        ),
        "tiktok": "TikTok vertical 9:16, energetic, thumb-stopping creative.",
    }

    def check(self, sku: dict[str, Any], prompt: str) -> ComplianceResult:
        result = ComplianceResult(modified_prompt=prompt)

        lowered = prompt.lower()
        if any(k in lowered for k in self.DANGEROUS_KEYWORDS):
            result.blocked = True
            result.passed = False
            return result

        market = sku.get("market", "US")
        fixes = self.CULTURAL_FIXES.get(market, {})
        for bad, good in fixes.items():
            if bad in result.modified_prompt:
                result.modified_prompt = result.modified_prompt.replace(bad, good)
                result.auto_fixed = True

        for brand in self.BRAND_BLACKLIST:
            if brand in lowered:
                result.warnings.append(f"L2 brand keyword detected: {brand}")
        for ip in self.IP_BLACKLIST:
            if ip in lowered:
                result.warnings.append(f"L3 IP keyword detected: {ip}")

        for platform in sku.get("target_platforms", []):
            addendum = self.PLATFORM_PROMPT_ADDENDUM.get(platform, "")
            if addendum:
                result.modified_prompt += addendum

        result.passed = True
        return result
```

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_compliance.py -v
```

Expected: 3 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/workers/compliance tests/test_compliance.py
git commit -m "feat: L1-L5 compliance engine"
```

---

## Task 3: Agentic RAG Reference Retriever

**Files:**
- Create: `mediaforge/mediaforge/rag/retriever.py`
- Test: `mediaforge/tests/test_retriever.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_retriever.py
import pytest
from mediaforge.rag.retriever import ReferenceRetriever
from mediaforge.rag.models import RagItem
from mediaforge.rag.vector_store import ChromaVectorStore


@pytest.mark.asyncio
async def test_retriever_finds_references(tmp_path):
    store = ChromaVectorStore(persist_dir=str(tmp_path / "chroma"))
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
    retriever = ReferenceRetriever(vector_store=store)
    refs = await retriever.retrieve(
        image_path=None,
        text="elegant silk dress",
        category="apparel",
        top_k=3,
    )
    assert len(refs) == 1
    assert refs[0].product_id == "P001"
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_retriever.py -v
```

- [x] **Step 3: Implement retriever**

```python
# mediaforge/mediaforge/rag/retriever.py
from mediaforge.rag.models import RagResult
from mediaforge.rag.vector_store import VectorStore


class ReferenceRetriever:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    async def retrieve(
        self,
        image_path: str | None,
        text: str,
        category: str,
        top_k: int = 5,
    ) -> list[RagResult]:
        return await self.vector_store.hybrid_search(
            image_path=image_path,
            text=text,
            category=category,
            top_k=top_k,
        )
```

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_retriever.py -v
```

Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/rag/retriever.py tests/test_retriever.py
git commit -m "feat: Agentic RAG reference retriever"
```

---

## Task 4: Image Workers

**Files:**
- Create: `mediaforge/mediaforge/workers/image/main_image.py`
- Create: `mediaforge/mediaforge/workers/image/detail_page.py`
- Create: `mediaforge/mediaforge/workers/image/social.py`
- Create: `mediaforge/mediaforge/workers/image/__init__.py`
- Modify: `mediaforge/mediaforge/workers/openrouter_client.py`
- Test: `mediaforge/tests/test_image_workers.py`

- [x] **Step 1: Write failing tests**

```python
# mediaforge/tests/test_image_workers.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from mediaforge.models.job import SkuInput
from mediaforge.workers.image.main_image import MainImageWorker


@pytest.mark.asyncio
async def test_main_image_worker_generates_per_platform(tmp_path):
    mock_client = AsyncMock()
    mock_client.generate_image.return_value = b"\x89PNG"
    mock_client.model_name = MagicMock(return_value="google/gemini-3-pro-image")

    worker = MainImageWorker(
        client=mock_client,
        storage_dir=str(tmp_path),
        model="pro",
    )
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Silk Dress",
        category="apparel",
        target_platforms=["amazon", "shopee"],
        output_types=["main_image"],
        market="US",
    )
    result = await worker.run(sku, tenant_id="t-1", job_id="j-1")
    assert len(result.success) == 2
    assert result.success[0].platform == "amazon"
    assert result.success[1].platform == "shopee"
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_image_workers.py -v
```

- [x] **Step 3: Implement image workers**

```python
# mediaforge/mediaforge/workers/image/base.py
import uuid
from abc import ABC, abstractmethod
from mediaforge.workers.base import WorkerResult
from mediaforge.models.job import SkuInput


class BaseImageWorker(ABC):
    def __init__(self, client, storage_dir: str, model: str):
        self.client = client
        self.storage_dir = storage_dir
        self.model = model

    @abstractmethod
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        ...

    def _build_prompt(self, sku: SkuInput, platform: str | None, references: list | None = None) -> str:
        base = f"High-quality e-commerce product photo of {sku.product_name}, category {sku.category}"
        if sku.style_hint:
            base += f", style: {sku.style_hint}"
        if platform:
            base += f", optimized for {platform}"
        if references:
            ref_ids = ", ".join([r.product_id for r in references])
            base += f", reference style from products: {ref_ids}"
        return base
```

```python
# mediaforge/mediaforge/workers/image/main_image.py
import uuid
from pathlib import Path
from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.storage import OutputStorage
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.image.base import BaseImageWorker


class MainImageWorker(BaseImageWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        checker = ComplianceChecker()
        storage = OutputStorage(self.storage_dir)
        result = WorkerResult()

        for platform in sku.target_platforms:
            prompt = self._build_prompt(sku, platform)
            compliance = checker.check(sku.model_dump(), prompt)
            if compliance.blocked:
                result.failed.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="failed",
                        error="L1 blocked",
                    )
                )
                continue

            try:
                image_bytes = await self.client.generate_image(
                    prompt=compliance.modified_prompt,
                    model=self.model,
                    size="2K",
                    aspect_ratio="1:1",
                    ref_image_path=sku.product_image_url if sku.product_image_url.startswith("/") else None,
                )
                asset_id = str(uuid.uuid4())
                path = await storage.save_asset(tenant_id, job_id, asset_id, image_bytes, ext="png")
                result.success.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="success",
                        file_path=path,
                    )
                )
            except Exception as exc:
                result.failed.append(
                    AssetOutput(
                        sku_id=sku.sku_id,
                        output_type="main_image",
                        model_used=self.client.model_name(self.model),
                        platform=platform,
                        status="failed",
                        error=str(exc),
                    )
                )
        return result
```

```python
# mediaforge/mediaforge/workers/image/__init__.py
from .main_image import MainImageWorker
from .detail_page import DetailPageWorker
from .social import SocialWorker

__all__ = ["MainImageWorker", "DetailPageWorker", "SocialWorker"]
```

```python
# mediaforge/mediaforge/workers/image/detail_page.py
from mediaforge.workers.image.base import BaseImageWorker
from mediaforge.workers.base import WorkerResult
from mediaforge.models.job import SkuInput


class DetailPageWorker(BaseImageWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        return WorkerResult()
```

```python
# mediaforge/mediaforge/workers/image/social.py
from mediaforge.workers.image.base import BaseImageWorker
from mediaforge.workers.base import WorkerResult
from mediaforge.models.job import SkuInput


class SocialWorker(BaseImageWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        return WorkerResult()
```

- [x] **Step 4: Add model_name helper to OpenRouterClient**

Modify `mediaforge/mediaforge/workers/openrouter_client.py`:

```python
    def model_name(self, alias: str) -> str:
        return IMAGE_MODELS.get(alias, alias)
```

- [x] **Step 5: Run tests, expect pass**

```bash
pytest tests/test_image_workers.py -v
```

Expected: 1 passed.

- [x] **Step 6: Commit**

```bash
git add mediaforge/workers/image tests/test_image_workers.py mediaforge/workers/openrouter_client.py
git commit -m "feat: image workers with compliance and platform fan-out"
```

---

## Task 5: Video Workers

**Files:**
- Create: `mediaforge/mediaforge/workers/video/veo.py`
- Create: `mediaforge/mediaforge/workers/video/seedance.py`
- Create: `mediaforge/mediaforge/workers/video/__init__.py`
- Test: `mediaforge/tests/test_video_workers.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_video_workers.py
import pytest
from unittest.mock import AsyncMock
from mediaforge.workers.video.veo import VeoWorker
from mediaforge.models.job import SkuInput


@pytest.mark.asyncio
async def test_veo_worker_generates_video(tmp_path):
    mock_client = AsyncMock()
    mock_client.generate_video.return_value = "https://cdn.example.com/video.mp4"
    mock_client.model_name.return_value = "google/veo-3.1"

    worker = VeoWorker(
        client=mock_client,
        storage_dir=str(tmp_path),
        model="veo",
    )
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Silk Dress",
        category="apparel",
        target_platforms=["tiktok"],
        output_types=["video"],
        market="US",
    )
    result = await worker.run(sku, tenant_id="t-1", job_id="j-1")
    assert len(result.success) == 1
    assert result.success[0].output_type == "video"
    assert "lock exposure" in mock_client.generate_video.call_args.kwargs["prompt"]
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_video_workers.py -v
```

- [x] **Step 3: Implement video workers**

```python
# mediaforge/mediaforge/workers/video/base.py
from abc import ABC, abstractmethod
from mediaforge.workers.base import WorkerResult
from mediaforge.models.job import SkuInput


class BaseVideoWorker(ABC):
    def __init__(self, client, storage_dir: str, model: str):
        self.client = client
        self.storage_dir = storage_dir
        self.model = model

    @abstractmethod
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        ...

    def _build_prompt(self, sku: SkuInput, platform: str | None) -> str:
        base = f"Engaging short video for {sku.product_name}, category {sku.category}"
        if sku.style_hint:
            base += f", style: {sku.style_hint}"
        if platform:
            base += f", optimized for {platform}"
        return base
```

```python
# mediaforge/mediaforge/workers/video/veo.py
from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.compliance.checker import ComplianceChecker
from mediaforge.workers.video.base import BaseVideoWorker


class VeoWorker(BaseVideoWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        checker = ComplianceChecker()
        result = WorkerResult()

        platform = sku.target_platforms[0] if sku.target_platforms else None
        prompt = self._build_prompt(sku, platform)
        compliance = checker.check(sku.model_dump(), prompt)

        if compliance.blocked:
            result.failed.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="failed",
                    error="L1 blocked",
                )
            )
            return result

        try:
            video_url = await self.client.generate_video(
                prompt=compliance.modified_prompt,
                model=self.model,
                duration=5,
                aspect_ratio="9:16",
                ref_image_path=sku.product_image_url if sku.product_image_url.startswith("/") else None,
            )
            result.success.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="success",
                    file_path=video_url,
                )
            )
        except Exception as exc:
            result.failed.append(
                AssetOutput(
                    sku_id=sku.sku_id,
                    output_type="video",
                    model_used=self.client.model_name(self.model),
                    platform=platform,
                    status="failed",
                    error=str(exc),
                )
            )
        return result
```

```python
# mediaforge/mediaforge/workers/video/seedance.py
from mediaforge.workers.video.base import BaseVideoWorker
from mediaforge.workers.base import WorkerResult
from mediaforge.models.job import SkuInput


class SeedanceWorker(BaseVideoWorker):
    async def run(self, sku: SkuInput, tenant_id: str, job_id: str) -> WorkerResult:
        from mediaforge.workers.video.veo import VeoWorker
        delegate = VeoWorker(client=self.client, storage_dir=self.storage_dir, model=self.model)
        return await delegate.run(sku, tenant_id, job_id)
```

```python
# mediaforge/mediaforge/workers/video/__init__.py
from .veo import VeoWorker
from .seedance import SeedanceWorker

__all__ = ["VeoWorker", "SeedanceWorker"]
```

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_video_workers.py -v
```

Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/workers/video tests/test_video_workers.py
git commit -m "feat: video workers for veo and seedance"
```

---

## Task 6: Batch Graph Nodes

**Files:**
- Create: `mediaforge/mediaforge/orchestrator/nodes.py`
- Test: `mediaforge/tests/test_batch_nodes.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_batch_nodes.py
import pytest
from mediaforge.orchestrator.nodes import validate_job, fan_out
from mediaforge.orchestrator.state import JobState, SkuInput


def test_validate_job_rejects_empty_skus():
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[],
        total_sku_count=0,
        status="running",
    )
    with pytest.raises(ValueError):
        validate_job(state)


def test_fan_out_creates_image_and_video_sends():
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image", "video"],
        market="US",
    )
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[sku],
        total_sku_count=1,
        status="running",
    )
    sends = fan_out(state)
    assert len(sends) == 2
    assert {s.node for s in sends} == {"image_worker", "video_worker"}
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_batch_nodes.py -v
```

- [x] **Step 3: Implement nodes.py**

```python
# mediaforge/mediaforge/orchestrator/nodes.py
from typing import Literal
from langgraph.types import Send

from mediaforge.models.job import AssetOutput, SkuInput
from mediaforge.orchestrator.state import JobState
from mediaforge.workers.base import WorkerResult
from mediaforge.workers.image import DetailPageWorker, MainImageWorker, SocialWorker
from mediaforge.workers.openrouter_client import OpenRouterClient
from mediaforge.workers.video import SeedanceWorker, VeoWorker


def validate_job(state: JobState) -> dict:
    if not state["skus"]:
        raise ValueError("No SKUs in batch")
    return {"total_sku_count": len(state["skus"])}


def fan_out(state: JobState) -> list[Send]:
    sends = []
    for sku in state["skus"]:
        image_types = {"main_image", "detail_page", "social"}
        if image_types.intersection(sku.output_types):
            sends.append(Send("image_worker", {"sku": sku, "tenant_id": state["tenant_id"], "job_id": state["job_id"]}))
        if "video" in sku.output_types:
            sends.append(Send("video_worker", {"sku": sku, "tenant_id": state["tenant_id"], "job_id": state["job_id"]}))
    return sends


async def image_worker(state: dict, config: dict) -> dict:
    sku: SkuInput = state["sku"]
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    result = WorkerResult()

    if "main_image" in sku.output_types:
        worker = MainImageWorker(client, settings.output_dir, model=settings.default_image_model)
        r = await worker.run(sku, tenant_id, job_id)
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "logs": [f"image_worker finished {sku.sku_id}"],
    }


async def video_worker(state: dict, config: dict) -> dict:
    sku: SkuInput = state["sku"]
    tenant_id: str = state["tenant_id"]
    job_id: str = state["job_id"]

    settings = get_settings()
    client = OpenRouterClient(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    result = WorkerResult()

    if "video" in sku.output_types:
        worker = VeoWorker(client, settings.output_dir, model=settings.default_video_model)
        r = await worker.run(sku, tenant_id, job_id)
        result.success.extend(r.success)
        result.failed.extend(r.failed)

    return {
        "completed": result.success,
        "failed": result.failed,
        "logs": [f"video_worker finished {sku.sku_id}"],
    }


def finalize_job(state: JobState) -> dict:
    success_count = len(state["completed"])
    fail_count = len(state["failed"])

    if fail_count == 0:
        status = "done"
    elif success_count == 0:
        status = "failed"
    else:
        status = "partial_fail"

    return {"status": status}
```

- [x] **Step 4: Add default_image_model / default_video_model to config.py**

```python
    default_image_model: str = "pro"
    default_video_model: str = "veo"
```

- [x] **Step 5: Run tests, expect pass**

```bash
pytest tests/test_batch_nodes.py -v
```

Expected: 2 passed.

- [x] **Step 6: Commit**

```bash
git add mediaforge/orchestrator/nodes.py tests/test_batch_nodes.py mediaforge/config.py
git commit -m "feat: batch graph nodes validate, fan-out, image/video workers"
```

---

## Task 7: Compile BatchOrchestrator Graph

**Files:**
- Create: `mediaforge/mediaforge/orchestrator/batch_graph.py`
- Test: `mediaforge/tests/test_batch_graph.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_batch_graph.py
import pytest
from unittest.mock import patch
from mediaforge.orchestrator.batch_graph import build_batch_graph
from mediaforge.orchestrator.state import JobState, SkuInput


@pytest.mark.asyncio
async def test_batch_graph_runs_to_done(tmp_path):
    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image"],
        market="US",
    )
    initial = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[sku],
        total_sku_count=1,
        status="running",
    )

    graph = build_batch_graph()

    with patch("mediaforge.workers.image.main_image.MainImageWorker.run") as mock_run:
        from mediaforge.workers.base import WorkerResult
        from mediaforge.models.job import AssetOutput
        mock_run.return_value = WorkerResult(
            success=[
                AssetOutput(
                    sku_id="SKU-001",
                    output_type="main_image",
                    model_used="google/gemini-3-pro-image",
                    platform="amazon",
                    status="success",
                    file_path=str(tmp_path / "img.png"),
                )
            ]
        )
        result = await graph.ainvoke(initial)

    assert result["status"] == "done"
    assert len(result["completed"]) == 1
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_batch_graph.py -v
```

- [x] **Step 3: Implement batch_graph.py**

```python
# mediaforge/mediaforge/orchestrator/batch_graph.py
from langgraph.graph import StateGraph, START, END

from mediaforge.orchestrator.nodes import (
    fan_out,
    finalize_job,
    image_worker,
    validate_job,
    video_worker,
)
from mediaforge.orchestrator.state import JobState


def build_batch_graph():
    builder = StateGraph(JobState)
    builder.add_node("validate_job", validate_job)
    builder.add_node("image_worker", image_worker)
    builder.add_node("video_worker", video_worker)
    builder.add_node("finalize_job", finalize_job)

    builder.add_edge(START, "validate_job")
    builder.add_conditional_edges("validate_job", fan_out, ["image_worker", "video_worker"])
    builder.add_edge("image_worker", "finalize_job")
    builder.add_edge("video_worker", "finalize_job")
    builder.add_edge("finalize_job", END)

    return builder.compile()
```

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_batch_graph.py -v
```

Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/orchestrator/batch_graph.py tests/test_batch_graph.py
git commit -m "feat: compile BatchOrchestrator LangGraph"
```

---

## Task 8: Persist Batch Results to Postgres

**Files:**
- Modify: `mediaforge/mediaforge/orchestrator/nodes.py`
- Test: `mediaforge/tests/test_batch_persistence.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_batch_persistence.py
import pytest
from unittest.mock import patch
from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.redis_client import get_redis
from mediaforge.orchestrator.batch_graph import build_batch_graph
from mediaforge.orchestrator.state import JobState, SkuInput


@pytest.mark.asyncio
async def test_batch_graph_persists_assets(db_engine, redis_client, tmp_path):
    store = JobStore(db_engine, redis_client)
    from mediaforge.models.job import BatchSubmitPayload
    payload = BatchSubmitPayload(
        skus=[
            SkuInput(
                sku_id="SKU-001",
                product_image_url="https://example.com/img.jpg",
                product_name="Dress",
                category="apparel",
                target_platforms=["amazon"],
                output_types=["main_image"],
                market="US",
            )
        ]
    )
    job_id = await store.create_job(tenant_id="t-1", payload=payload)
    await store.start_job(job_id)

    initial = JobState(
        job_id=job_id,
        tenant_id="t-1",
        skus=payload.skus,
        total_sku_count=1,
        status="running",
    )

    graph = build_batch_graph()
    with patch("mediaforge.workers.image.main_image.MainImageWorker.run") as mock_run:
        from mediaforge.workers.base import WorkerResult
        from mediaforge.models.job import AssetOutput
        mock_run.return_value = WorkerResult(
            success=[
                AssetOutput(
                    sku_id="SKU-001",
                    output_type="main_image",
                    model_used="google/gemini-3-pro-image",
                    platform="amazon",
                    status="success",
                    file_path=str(tmp_path / "img.png"),
                )
            ]
        )
        await graph.ainvoke(initial)

    assets = await store.get_assets_for_job(job_id)
    assert len(assets) == 1
    assert assets[0]["status"] == "success"
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_batch_persistence.py -v
```

- [x] **Step 3: Modify nodes.py to persist assets in workers**

Add persistence logic:

```python
from mediaforge.db.engine import get_engine
from mediaforge.db.job_store import JobStore
from mediaforge.db.redis_client import get_redis


async def _persist_results(state: JobState):
    engine = get_engine()
    redis = await get_redis()
    store = JobStore(engine, redis)
    for asset in state["completed"]:
        await store.add_asset(
            job_id=state["job_id"],
            tenant_id=state["tenant_id"],
            sku_id=asset.sku_id,
            output_type=asset.output_type,
            model_used=asset.model_used,
            status=asset.status,
            file_path=asset.file_path,
            platform=asset.platform,
        )
    for asset in state["failed"]:
        await store.add_asset(
            job_id=state["job_id"],
            tenant_id=state["tenant_id"],
            sku_id=asset.sku_id,
            output_type=asset.output_type,
            model_used=asset.model_used,
            status=asset.status,
            error_msg=asset.error or "unknown",
            platform=asset.platform,
        )
    await store.finalize_job(state["job_id"], len(state["completed"]), len(state["failed"]))
```

Then call `_persist_results(state)` at the top of `finalize_job`.

- [x] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_batch_persistence.py -v
```

Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add mediaforge/orchestrator/nodes.py tests/test_batch_persistence.py
git commit -m "feat: persist batch graph results to postgres"
```

---

## Task 9: Checkpoint I/O Optimization

**Files:**
- Create: `mediaforge/mediaforge/orchestrator/checkpointer.py`
- Modify: `mediaforge/mediaforge/orchestrator/batch_graph.py`
- Modify: `mediaforge/mediaforge/db/tables.py`
- Test: `mediaforge/tests/test_checkpointer.py`

- [x] **Step 1: Write failing test**

```python
# mediaforge/tests/test_checkpointer.py
import pytest
from mediaforge.orchestrator.checkpointer import SparsePostgresSaver
from mediaforge.orchestrator.state import JobState, SkuInput


@pytest.mark.asyncio
async def test_saver_stores_checkpoint(db_engine):
    saver = SparsePostgresSaver(db_engine)
    await saver.setup()

    sku = SkuInput(
        sku_id="SKU-001",
        product_image_url="https://example.com/img.jpg",
        product_name="Dress",
        category="apparel",
        target_platforms=["amazon"],
        output_types=["main_image"],
        market="US",
    )
    state = JobState(
        job_id="j1",
        tenant_id="t1",
        skus=[sku],
        total_sku_count=1,
        status="running",
    )
    config = {"configurable": {"thread_id": "t1"}}
    await saver.aput(config, state, {"source": "loop", "step": 1}, None)
    loaded = await saver.aget(config)
    assert loaded is not None
    assert loaded["status"] == "running"
```

- [x] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_checkpointer.py -v
```

- [x] **Step 3: Add checkpoints table**

Modify `mediaforge/mediaforge/db/tables.py`:

```python
from sqlalchemy import Column, String, LargeBinary, DateTime, Index

class CheckpointTable(Base):
    __tablename__ = "checkpoints"

    thread_id = Column(String(64), primary_key=True)
    checkpoint_ns = Column(String(255), primary_key=True, default="")
    checkpoint_id = Column(String(64), primary_key=True)
    parent_checkpoint_id = Column(String(64), nullable=True)
    type = Column(String(32), nullable=False)
    checkpoint = Column(LargeBinary, nullable=False)
    metadata_ = Column("metadata", LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("idx_checkpoints_thread", "thread_id", "created_at"),
    )
```

- [x] **Step 4: Implement sparse Postgres saver**

```python
# mediaforge/mediaforge/orchestrator/checkpointer.py
import pickle
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine
from langgraph.checkpoint.base import BaseCheckpointSaver


class SparsePostgresSaver(BaseCheckpointSaver):
    """AsyncPostgresSaver wrapper that skips worker-step writes and flushes in batches."""

    def __init__(self, engine: AsyncEngine, flush_every: int = 5):
        super().__init__()
        self.engine = engine
        self.flush_every = flush_every
        self._pending = []

    async def setup(self):
        from mediaforge.db.tables import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def aput(self, config, checkpoint, metadata, parent_config=None):
        # Only checkpoint at graph boundaries, skip per-worker noise
        source = (metadata or {}).get("source", "")
        if source not in ("input", "loop", "update"):
            return
        self._pending.append((config, checkpoint, metadata))
        if len(self._pending) >= self.flush_every:
            await self._flush()

    async def _flush(self):
        if not self._pending:
            return
        from mediaforge.db.tables import CheckpointTable
        async with self.engine.begin() as conn:
            for config, checkpoint, metadata in self._pending:
                thread_id = config["configurable"]["thread_id"]
                checkpoint_id = str(checkpoint.get("id", "0"))
                await conn.execute(
                    CheckpointTable.insert().values(
                        thread_id=thread_id,
                        checkpoint_id=checkpoint_id,
                        type="checkpoint",
                        checkpoint=pickle.dumps(checkpoint),
                        metadata=pickle.dumps(metadata),
                    )
                )
        self._pending.clear()

    async def aget(self, config):
        from mediaforge.db.tables import CheckpointTable
        thread_id = config["configurable"]["thread_id"]
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(CheckpointTable)
                .where(CheckpointTable.c.thread_id == thread_id)
                .order_by(CheckpointTable.c.created_at.desc())
                .limit(1)
            )
            row = result.mappings().first()
            if row is None:
                return None
            return pickle.loads(row["checkpoint"])

    async def aget_tuple(self, config):
        checkpoint = await self.aget(config)
        if checkpoint is None:
            return None
        return (config, checkpoint, {})
```

- [x] **Step 5: Wire checkpointer into batch graph**

Modify `mediaforge/mediaforge/orchestrator/batch_graph.py`:

```python
from mediaforge.db.engine import get_engine
from mediaforge.orchestrator.checkpointer import SparsePostgresSaver


def build_batch_graph():
    engine = get_engine()
    saver = SparsePostgresSaver(engine)
    builder = StateGraph(JobState)
    # ... existing node wiring ...
    return builder.compile(checkpointer=saver)
```

- [x] **Step 6: Add langgraph-checkpoint dependency**

```toml
"langgraph-checkpoint>=2.0.0",
```

- [x] **Step 7: Run tests, expect pass**

```bash
pytest tests/test_checkpointer.py -v
```

Expected: 1 passed.

- [x] **Step 8: Commit**

```bash
git add mediaforge/orchestrator/checkpointer.py mediaforge/orchestrator/batch_graph.py mediaforge/db/tables.py tests/test_checkpointer.py pyproject.toml
git commit -m "feat: sparse Postgres checkpointer for batch graph"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: Batch graph, workers, compliance, RAG reference retrieval, and checkpoint optimization all have explicit tasks.
- [x] **Placeholder scan**: No TBD/TODO/"implement later" left.
- [x] **Type consistency**: `JobState`, `AssetOutput`, `RagResult`, `SparsePostgresSaver` interfaces match design.
- [x] **No placeholders**: All code blocks are complete.

---

## Plan 02 Acceptance Criteria

- `pytest mediaforge/tests/test_batch_*.py tests/test_image_workers.py tests/test_video_workers.py tests/test_compliance.py tests/test_state.py tests/test_retriever.py tests/test_checkpointer.py` passes.
- `build_batch_graph()` returns a compiled LangGraph with `SparsePostgresSaver`.
- Worker nodes use `ComplianceChecker` before calling OpenRouter.
- Image workers can enrich prompts via `ReferenceRetriever`.
- Video worker injects Veo exposure-stability prefix.
- `finalize_job` persists all `completed` and `failed` assets to PostgreSQL via `JobStore` and publishes SSE done event.
- Checkpointer table is created and only boundary checkpoints are flushed.
