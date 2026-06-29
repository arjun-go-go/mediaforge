# MediaForge

> 面向跨境电商的 AI 创意内容批量生成平台 — FastAPI · LangGraph · Celery · Next.js

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-FF6B35)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

MediaForge 是一套面向电商场景的多租户 AI 创意工作台，提供**批量产品图生成**、**短视频生成**、**风格参考检索**与**智能助手对话**四类核心能力。后端基于 FastAPI + Celery + LangGraph 构建，前端使用 Next.js 14 + Tailwind CSS。

---

## ✨ 核心特性

- 🎨 **批量产品图生成** — 单次最多支持 100 SKU 并行，通过 Celery 多优先级队列调度
- 🖼️ **三种图像产物** — 主图 (hero shot) / 详情页 (场景+卖点+细节三视图) / 社交素材 (TikTok·抖音·小红书·Instagram 平台化创意)
- 📐 **平台感知比例** — `tiktok` → 9:16、`xiaohongshu` → 3:4、`amazon` → 1:1 自动匹配
- 🎬 **短视频生成** — 集成 Google Veo / ByteDance Seedance（可选）
- 🧠 **多 Agent 智能调度** — 基于 LangGraph Supervisor 模式，自动路由到 image / video / RAG / compliance 专家
- 🔍 **三路混合检索（Hybrid Search）** — 文本密集向量 + 图像密集向量 + TF-IDF 稀疏向量，RRF 融合
- 🛡️ **场景感知合规** — 用户提供创意 style_hint 时自动放宽平台版式硬规则，避免"江南水乡"被强制改成"纯白棚拍"
- 🔒 **完整的多租户体系** — JWT + Refresh Token + API Key + 配额管控 + 审计日志
- 📦 **可插拔的向量库** — 默认 Chroma 本地开发，生产推荐 Milvus / Zilliz Cloud
- 🛡️ **企业级安全** — CSRF 双提交、JTI 黑名单、登录失败锁定、合规校验
- 📊 **可观测性** — 结构化日志 + 请求 trace_id + 费用追踪 + SSE 实时进度推送

---

## 📸 项目截图

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/f5a9bd4e-9cb5-45ab-9883-ec26f26d4918.jpeg" alt="批量提交" width="100%" />
      <br/>
      <sub><b>批量提交</b> — SKU 表单填写，支持上传产品图、选择输出类型与目标平台</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/94f1f466-4efb-4dd6-ab60-a883ddb034e7.jpeg" alt="任务详情" width="100%" />
      <br/>
      <sub><b>任务详情</b> — 提交内容 + 生成素材双视图，点击图片可放大下载</sub>
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <img src="docs/screenshots/3c08fe46-fcc0-4ed3-af00-6b01bd560b85.jpeg" alt="智能助手" width="60%" />
      <br/>
      <sub><b>智能助手</b> — LangGraph 多 Agent 调度，SSE 流式输出，图片可点击放大</sub>
    </td>
  </tr>
</table>

---

## 🏗️ 技术架构

```
                    ┌─────────────────┐
                    │   Next.js 14    │   前端 (React + Tailwind + Zustand)
                    │   (App Router)  │
                    └────────┬────────┘
                             │ HTTPS / SSE
                    ┌────────▼────────┐
                    │     Gunicorn    │   反向代理 + 多 worker
                    │  + UvicornWorker│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     FastAPI     │   认证 / 路由 / 限流 / CSRF
                    └────┬───────┬────┘
                         │       │
            ┌────────────┘       └────────────┐
            ▼                                 ▼
   ┌─────────────────┐               ┌─────────────────┐
   │   PostgreSQL    │               │ Celery Worker   │
   │ (用户/任务/审计) │               │ (LangGraph 调度)│
   └─────────────────┘               └────────┬────────┘
                                              │
   ┌─────────────────┐               ┌────────▼────────┐
   │ Milvus / Chroma │◄──────────────│  OpenRouter /   │
   │   (向量检索)     │               │  Vertex AI 等   │
   └─────────────────┘               └─────────────────┘

   ┌─────────────────┐
   │      Redis      │   缓存 / Session / Pub/Sub / Celery Broker
   └─────────────────┘
```

### 技术栈

**后端**
- 框架：FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async)
- 任务调度：Celery 5 + Redis Broker
- Agent 编排：LangGraph 1.2 + LangChain
- 数据库：PostgreSQL 16 + Alembic 迁移
- 缓存：Redis 7（缓存/Session/Pub-Sub）
- 向量库：Milvus / Zilliz Cloud / Chroma
- Embedding：DashScope `text-embedding-v4`（1024 维）+ `qwen3-vl-embedding`（2560 维多模态）
- 部署：Gunicorn + Uvicorn

**前端**
- Next.js 14 (App Router) · React 18 · TypeScript
- Tailwind CSS · shadcn/ui · Zustand
- SSE 流式渲染 · CSRF 双提交

---

## 🎨 图像生成流水线

每个 SKU 提交后，按以下规则展开为多张图：

```
SKU × output_types × target_platforms × shot_variant  →  N 张图
```

| 输出类型 | 拍摄变体 | 比例 | 适用平台 |
|---------|---------|------|---------|
| **主图** `main_image` | hero shot | 跟随平台 | 全平台 |
| **详情页** `detail_page` | scene · feature · closeup（3 张） | 3:4 | 全平台 |
| **社交素材** `social` | 平台化创意 | 跟随平台 | 仅 social 白名单 |

**Prompt 组装顺序**：`base → style_hint → platform → shot_suffix → compliance → 防水印`

- **场景感知合规**：当 `style_hint` 含 `江南/水乡/外景/lifestyle/...` 等关键词时，平台严格版式规则（如 Amazon "纯白背景"）自动切换为温和提示，让创意场景生效
- **防参考图水印**：每个 prompt 末尾追加"do not copy any text/watermark/logo from reference image"，避免 Gemini 多模态复刻产品图里的营销文字
- **平台 → 比例映射**：`workers/image/base.py` 内置 16 个主流平台映射

**举例**：勾选 `主图 + 详情页`，平台选 `tiktok, amazon`，每个 SKU 产出 **2 (主图) + 6 (详情页 3 变体 × 2 平台) = 8 张**。

---

## 🚀 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- PostgreSQL 16
- Redis 7

### 1. 克隆仓库

```bash
git clone https://github.com/arjun-go-go/mediaforge.git
cd mediaforge
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，必填项：

```bash
# 数据库 & 缓存
DATABASE_URL=postgresql+asyncpg://mediaforge:mediaforge@localhost:5432/mediaforge
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=<openssl rand -hex 32>

# OpenRouter (图片/视频生成模型代理)
OPENROUTER_API_KEY=sk-or-v1-xxx

# DashScope (向量化)
DASHSCOPE_API_KEY=sk-xxx

# 向量库（生产建议 milvus）
VECTOR_STORE_BACKEND=chroma   # 或 milvus
# MILVUS_URI=https://xxx.serverless.aws.cloud.zilliz.com
# MILVUS_TOKEN=xxx
```

### 3. 初始化数据库与种子数据

```bash
# 数据库迁移
python scripts/init_db.py

# 创建演示租户和用户
python scripts/seed_users.py

# 导入示例商品到向量库（40 个 SKU）
python scripts/seed_rag.py --file data/products.csv --image-dir images/
```

种子账号：
```
starter@mediaforge.dev    / Starter123!
pro@mediaforge.dev        / Pro123!
enterprise@mediaforge.dev / Enterprise123!
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:3000 即可访问。

---

## 🖥️ 本地开发（不使用 Docker）

```bash
# 1. 安装依赖（推荐 uv）
pip install -e ".[dev]"
# 或
uv pip install -e ".[dev]"

# 2. 启动 API（开发模式）
uvicorn mediaforge.gateway.main:app --reload --port 8000

# 3. 启动 Celery Worker（Windows 必须用 --pool=solo）
celery -A mediaforge.celery_app worker --pool=solo -Q normal,high,low -l info

# 4. 启动 Celery Beat（可选，定时任务）
celery -A mediaforge.celery_app beat -l info
```

---

## 📂 项目结构

```
mediaforge/
├── mediaforge/                  # 后端主包
│   ├── auth/                    # JWT / API Key / 密码哈希 / Session 缓存
│   ├── config.py                # Pydantic Settings 配置中心
│   ├── db/                      # SQLAlchemy 模型 / Store 层
│   ├── gateway/                 # FastAPI 应用
│   │   ├── main.py              # ASGI 入口
│   │   ├── middleware/          # 限流 / CSRF / 防注入 / 可观测
│   │   └── routers/             # 路由：auth/batch/agent/rag/tasks/api_keys/...
│   ├── models/                  # Pydantic 业务模型
│   ├── observability/           # 费用追踪 / 指标
│   ├── orchestrator/            # LangGraph 图编排
│   │   ├── agent_graph.py       # Supervisor + 4 个专家 agent
│   │   ├── batch_graph.py       # 批量任务 LangGraph
│   │   ├── nodes.py             # validate / fan_out / image_worker / finalize
│   │   └── tasks.py             # Celery 入口
│   ├── rag/                     # 向量检索
│   │   ├── embeddings.py        # DashScope 文本/图像 embedding
│   │   ├── milvus_store.py      # Milvus 实现
│   │   ├── chroma_store.py      # Chroma 实现
│   │   └── ingest.py            # 数据入库
│   ├── workers/                 # 模型调用器
│   │   ├── openrouter_client.py # OpenRouter HTTP 客户端
│   │   ├── image/               # 主图 / 详情页 / 社交图
│   │   ├── video/               # Veo / Seedance
│   │   └── compliance/          # 合规检查器
│   └── celery_app.py            # Celery 配置
├── frontend/                    # Next.js 14 前端
│   ├── src/app/                 # App Router 页面
│   ├── src/components/          # UI 组件 (shadcn/ui)
│   ├── src/lib/api.ts           # API 客户端 + SSE 流
│   └── src/store/               # Zustand 状态管理
├── alembic/                     # 数据库迁移
├── scripts/                     # 运维脚本（init_db / seed_users / seed_rag）
├── tests/                       # 单元 + 集成测试（pytest）
├── data/                        # 示例数据
├── images/                      # 示例 SKU 图片
├── docker-compose.yml
├── Dockerfile
├── gunicorn.conf.py
└── pyproject.toml
```

---

## 🔑 核心接口

| 模块 | 接口 | 说明 |
|---|---|---|
| **认证** | `POST /api/v1/auth/login` | 用户登录，返回 JWT + Refresh + CSRF |
| | `POST /api/v1/auth/refresh` | 静默刷新 access token |
| | `POST /api/v1/auth/logout` | 登出（黑名单 JTI） |
| **批量任务** | `POST /api/v1/batch/submit` | 提交批量生成任务（最多 5000 SKU） |
| | `GET /api/v1/tasks` | 任务列表 |
| | `GET /api/v1/tasks/{job_id}` | 任务详情（含 input + assets） |
| | `GET /api/v1/tasks/{job_id}/stream` | SSE 实时进度 |
| | `DELETE /api/v1/tasks/{job_id}` | 删除单个任务（仅终态） |
| | `DELETE /api/v1/tasks/failed` | 批量清理失败任务 |
| **智能助手** | `POST /api/v1/agent/chat` | SSE 多轮对话 |
| | `GET /api/v1/agent/history` | 加载历史 |
| **RAG** | `POST /api/v1/rag/search` | 三路混合检索 |
| | `POST /api/v1/rag/ingest` | CSV/Excel 入库 |
| **API Key** | `POST /api/v1/api-keys` | 创建租户 API 密钥 |
| **上传** | `POST /api/v1/upload` | 上传产品参考图 |

完整 OpenAPI 文档：启动后访问 http://localhost:8000/docs

---

## 🧪 测试

```bash
# 全部测试
pytest

# 指定模块
pytest tests/test_auth.py -v

# 覆盖率
pytest --cov=mediaforge --cov-report=html
```

---

## 🛠️ 配置项说明

详见 `mediaforge/config.py`，关键配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `JWT_ACCESS_EXPIRES_SECONDS` | 1800 | Access token 有效期（秒） |
| `JWT_REFRESH_EXPIRES_SECONDS` | 604800 | Refresh token 有效期（7 天） |
| `IMAGE_MODEL_PRO` | `google/gemini-3.1-flash-image` | Pro 图片模型别名 |
| `IMAGE_MODEL_FAST` | `openai/gpt-5-image-mini` | Fast 图片模型别名 |
| `SEMAPHORE_GEMINI_PRO_IMAGE` | 4 | 单进程内 Pro 模型并发上限 |
| `VECTOR_STORE_BACKEND` | `chroma` | 向量库后端 (`chroma` / `milvus`) |
| `STORAGE_BACKEND` | `local` | 资源存储 (`local` / `s3`) |
| `BACKCOMPAT_DEMO_KEYS` | `true` | 开发期是否允许内置 demo API Key |

---

## 📈 性能与扩缩容

**单机基准**（4 进程 Gunicorn / Intel i7 / 32GB）：
- 静态接口：1000+ QPS
- 批量提交：~500 QPS（受 PG 写入限制）
- 单 SKU 生图：8~20 秒（受 OpenRouter 上游限制）

**水平扩展建议**：
- API 层：无状态，可任意扩 Gunicorn 实例
- Worker 层：按队列 (`high` / `normal` / `low`) 拆 Celery 池
- DB：主写 + 只读副本，RAG / 审计走只读
- Redis：缓存与 broker 拆为独立实例（已在 `docker-compose.yml` 中拆分）
- 对象存储：生产环境必须切换到 `STORAGE_BACKEND=s3`

---

## 🗺️ 路线图

- [x] 三路混合检索（文本 + 图像 + 稀疏）
- [x] LangGraph 多 Agent 调度
- [x] 任务批量删除 / 失败重试
- [x] 详情页 / 社交素材专业实现（3 拍摄变体、平台化创意）
- [x] 平台感知 aspect_ratio（TikTok 9:16、小红书 3:4、Amazon 1:1…）
- [x] 场景感知合规（创意 style_hint 时放宽平台硬规则）
- [x] Celery 事件循环资源隔离（每任务回收 DB 引擎 + httpx client）
- [ ] 上传图水印 OCR 检测（避免 Gemini 复刻营销文字）
- [ ] 以图搜图（图像 → 商品库相似检索）
- [ ] WebSocket 替代 SSE（更稳定的长连接）
- [ ] 对象存储多 backend（OSS / COS / R2）
- [ ] Prometheus + Grafana 监控面板
- [ ] 前端国际化（i18n）

---

## 📄 License

[MIT](LICENSE)

---

## 🙏 致谢

- [Fashion-AI](https://github.com/liangdabiao/Fashion-AI) — RAG + 图像生成流水线参考实现
