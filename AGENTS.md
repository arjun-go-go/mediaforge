# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## Workspace Overview

This repo contains 5 independent AI projects. Each has its own `项目详细说明.md` with full Chinese documentation.

| Project | Type | Language | Primary API |
|---------|------|----------|-------------|
| `Fashion-AI/` | RAG + image gen pipeline | Python | OpenRouter |
| `ecommerce-img-gen/` | LLM Skill package (ClawHub) | Python + Markdown | 1xm.ai |
| `Shoplive/` | Full-stack video gen workbench | Python (Flask) + JS | LiteLLM proxy + Vertex AI |
| `ecom-details-image/` | E-commerce detail page gen | Python | OpenRouter |
| `nano-banana-milvus/` | Hybrid vector search demo | Python | OpenRouter + Zilliz |

---

## Fashion-AI

### Working Directory

All `python main.py` commands must be run from `Fashion-AI/`, not the repo root.

### Run Commands

```bash
# Setup (build Milvus collection + encode + insert) — must run before search/generate
python main.py setup

# Test hybrid search for a new product
python main.py search --new-id NEW001

# Full pipeline (search → style analysis → image generation)
python main.py generate --new-id NEW001

# Generate with alternative image model
python main.py generate --new-id NEW001 --model gpt-image
```

### Required Environment Variables

Create `Fashion-AI/.env` from `.env.example`:
- `OPENROUTER_API_KEY` — OpenRouter API key (all models go through this)
- `MILVUS_HOST` — Zilliz Cloud URI (Milvus Lite does NOT work on Windows)
- `MILVUS_TOKEN` — Zilliz Cloud API token
- `COLLECTION_NAME` — Milvus collection name (defaults to `fashion_products`)

### Architecture Gotchas

- All models (embedding, LLM, image gen) are called via OpenRouter API, NOT directly. Embedding uses `requests.post` to `/api/v1/embeddings`, LLM uses `openai.OpenAI` client with `base_url="https://openrouter.ai/api/v1"`, image gen uses `requests.post` to `/api/v1/chat/completions`.
- Qwen 3.x thinking mode must be disabled: `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` in `style_analyzer.py`. Without this, the response lands in `reasoning_content` instead of `content`.
- Image gen payload must include `"modalities": ["image", "text"]`. Gemini models need `image_config` with `aspect_ratio` and `image_size`; OpenAI models only need `aspect_ratio`.
- OpenAI image models (gpt-image, gpt-image-pro, gpt-image-mini) require overseas network access — they fail with `unsupported_country` error in some regions. Default model `nano-banana` (Gemini) has no region restriction.
- `config.py` is the single source of truth for all settings. Model names, dimensions, defaults — all defined there. Do not hardcode them elsewhere.
- `setup` command drops and recreates the Milvus collection every run. Do not run it casually if the collection has data you want to preserve.
- TF-IDF is refit from `products.csv` on every `search`/`generate` call (not persisted). If CSV rows change without re-running `setup`, the query vocabulary diverges from the stored sparse vectors, causing silently wrong results.
- `generate_promo_photo()` only passes `ref_images[0]` (top-1 hit) to the image gen model, despite receiving a list of reference images.

### Key Technical Details

- Dense vectors: 2048-dim from `nvidia/llama-nemotron-embed-vl-1b-v2`, COSINE metric
- Sparse vectors: TF-IDF from `sklearn` (max 500 features), SPARSE_INVERTED_INDEX with IP metric
- Hybrid search uses `AnnSearchRequest` + `RRFRanker(k=60)` in `milvus_store.py`
- Default filter: `category == "{category}" and sales_count > 1500`
- Images are resized to max 512px for embedding, 1024px for generation prompts

---

## ecommerce-img-gen

ClawHub LLM Skill package (v2.6.0). Intelligence lives in Markdown docs under `references/`, not in Python code. The Python runtime (`scripts/generate_image.py`) is just a thin API wrapper.

### Run Commands

This is a Skill package — it is invoked by a ClawHub-compatible LLM agent, not run directly. For standalone testing:

```bash
cd ecommerce-img-gen
python scripts/generate_image.py  # reads API_KEY from env, prints generated image URL
```

### Required Environment Variables

- `1XM_API_KEY` — API key for 1xm.ai (wraps Google Gemini image models)

### Architecture Gotchas

- The Skill definition lives in `SKILL.md`. All routing logic, compliance rules, and prompt templates are in `references/*.md` — edit those files, not Python, to change behavior.
- Two models: `nano-banana-2` → `gemini-3.1-flash-image-preview` (default, up to 2K); `nano-banana-pro` → `gemini-3-pro-image-preview` (up to 4K). Switch via user request only.
- `generate_image.py` has a copy-paste bug: `os.environ.get("1XM_API_KEY") or os.environ.get("1XM_API_KEY")` — both branches read the same env var. Second branch was meant to read `OPENROUTER_API_KEY`.
- Compliance layers L2 (brand), L3 (copyright), and L6 (publish auth) require **human confirmation** — do not auto-fix. Only L4 (cultural taboos) is auto-corrected silently.
- Batch generation uses `ThreadPoolExecutor(max_workers=2)` — do not raise above 2 without testing rate limits.
- Cultural auto-fix rules: number 4 → 6 for China/Vietnam markets; 13 → 12 for Philippines; white/black backgrounds banned in some East Asian funeral contexts.

### Key Technical Details

- API endpoint: `POST https://1xm.ai/v1/chat/completions`
- Timeout: 180s, MAX_RETRIES: 10, RETRY_DELAY: 5s
- Image payload format: `"modalities": ["image", "text"]` required (same pattern as Fashion-AI)
- 6 visual styles: 极简白底 / 生活场景 / 轻奢简约 / 活力色彩 / 手绘插画 / UGC快节奏
- Style routing: brand category → style is defined in `references/styles_and_routing.md`

---

## Shoplive

Flask + Vanilla JS ES6 full-stack video generation workbench (~11,400 LOC backend). Run from `Shoplive/`.

### Run Commands

```bash
cd Shoplive
pip install -r requirements.txt
python -m shoplive.backend.web_app  # Flask dev server, port 5000
```

### Required Environment Variables

Create `Shoplive/.env`:
- `LITELLM_API_KEY` — key for LiteLLM proxy at `https://litellm.shoplazza.site`
- `GOOGLE_CLOUD_PROJECT` — GCP project for Vertex AI (Veo, Gemini)
- `GOOGLE_APPLICATION_CREDENTIALS` — path to GCP service account JSON
- `JIMENG_API_KEY` — ByteDance 即梦 video API key (optional)
- `TABCODE_API_KEY` — Grok Video via tabcode.cc (optional)

### Architecture Gotchas

- **God module**: `backend/web_app.py` is 730 lines. Each API domain registers its own routes via `register_X_routes(app, *, json_error, ...)` — find logic in the sub-modules, not in web_app.py.
- **No Gunicorn**: runs Flask dev server. All state is in-memory; a restart wipes caches. Do not deploy as-is.
- **Veo polling**: adaptive delays `[3, 5, 8, 12, 12]` seconds. Thread-local `requests.Session` for TLS reuse. Do not replace with a fixed `time.sleep`.
- **Veo exposure fix**: the string `"First 0-4 seconds: lock exposure and white balance"` is auto-appended to every Veo prompt to prevent opening flash — do not remove it.
- **Fixed compliance suffix**: every video prompt gets a hardcoded Chinese quality suffix appended (`高光边缘干净...不出现他牌标识或水印`). It is not user-configurable.
- **LLM proxy models**: Gemini 2.5 Flash + Claude 4.5 Haiku (Bedrock) via LiteLLM. Direct Vertex AI wrappers exist separately for streaming use cases.
- **Prompt splitting**: LLM-driven 3-step CoT splits prompts for 16s/12s multi-segment videos. Do not hand-write split logic.
- **ffmpeg dependency**: video editing (drawtext, speed, concat) requires `ffmpeg` on PATH. Font path resolution tries 6 candidate paths; add new fonts to that list in `helpers.py`.
- **Hot video remake**: uses Gemini 2.5 Flash for ASR with 24h cache. 12 regex patterns handle URL normalization across 6 video platforms.
- **Tests**: 370 tests, all mocked (zero real E2E). `pytest` from `Shoplive/` root.

### Key Technical Details

- 5 video backends: Google Veo 3.1, Grok Video (tabcode.cc), ByteDance 即梦, Lightricks LTX-Video 2.3, ComfyUI LTX 2.3
- 6 framework types: Product Showcase, UGC Review, Pain Point & Solution, Product Demo, Before-After, Brand Storytelling
- Agent API: SSE multi-round tool execution, 13+ tools, 4 skills, MCP JSON-RPC 2.0 at `/api/mcp/rpc`
- Veo flicker mitigation filter: `hqdn3d=4:3:6:4.5,fade=t=in:st=0:d=0.22`
- Caching: LLM response (300s), product insight (600s), ASR (24h), Veo chain jobs (3600s)
- Product scraper: dual-engine (requests + Playwright stealth), 11 platforms supported

---

## ecom-details-image

Generates e-commerce product detail page images. See `ecom-details-image/项目详细说明.md` for full docs.

### Required Environment Variables

- `OPENROUTER_API_KEY` — all model calls go through OpenRouter

---

## nano-banana-milvus

Hybrid vector search demo using Milvus/Zilliz. Shares the same core architecture as `Fashion-AI` (dense + sparse + RRF). See `nano-banana-milvus/项目详细说明.md` for full docs.

### Required Environment Variables

- `OPENROUTER_API_KEY` — embedding and LLM calls
- `MILVUS_HOST` / `MILVUS_TOKEN` — Zilliz Cloud (Milvus Lite does NOT work on Windows)
