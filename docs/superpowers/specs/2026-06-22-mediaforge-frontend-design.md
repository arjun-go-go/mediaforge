# MediaForge 前端设计文档

> 日期：2026-06-22  
> 范围：Next.js 14 前端 + 必要的后端补充接口

---

## 1. 目标

为 MediaForge 提供一套可直接部署的 Web 前端，覆盖用户从登录、任务提交、进度查看到 AI Agent 聊天的完整工作流。

---

## 2. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 框架 | Next.js 14 (App Router) | 与 Plan 05 Dockerfile 兼容，静态导出到 `dist/` |
| 语言 | TypeScript | 全链路类型安全 |
| 样式 | Tailwind CSS + shadcn/ui | 深色主题 + 珊瑚橙品牌色 |
| 状态 | Zustand | API Key、租户信息、主题、SSE 连接状态 |
| 图表 | Recharts | Dashboard 实时/历史统计图表 |
| 测试 | Vitest + React Testing Library | 组件与 Hook 测试 |
| SSE | fetch ReadableStream | 原生 `EventSource` 无法自定义 header |

---

## 3. 整体布局

```
+----------------+---------------------------+
|                |      Topbar               |
|                |  Brand | Tenant | Logout  |
|   Sidebar      +---------------------------+
|                |                           |
|   Dashboard    |                           |
|   Batch        |      Main Content         |
|   Tasks        |                           |
|   Agent        |                           |
|   Settings     |                           |
+----------------+---------------------------+
```

- **Sidebar**：固定左侧，图标 + 文字导航，当前项高亮。
- **Topbar**：左侧显示品牌，右侧显示当前 Tenant/Plan、API Key 快捷操作、退出。
- **主内容区**：根据路由渲染对应页面。

---

## 4. 页面设计

### 4.1 Login / Tenant 选择页

**功能：**
1. 用户输入 API Key。
2. 前端调用 `GET /api/v1/me`（新增）获取租户信息：
   - `tenant_id`、`name`、`plan`、`quotas`
3. 展示租户卡片：
   - Plan 徽章（starter / pro / enterprise）
   - 月度额度（image_credits_monthly、video_credits_monthly）
   - 并发任务上限、SKU 上限
4. 用户确认后进入应用；支持保存多个 API Key 并切换租户。
5. 错误处理：无效 Key 时显示 401 提示。

**状态存储：**
- `localStorage`：API Key 列表、当前选中 tenant_id
- Zustand：当前 tenant、是否已认证

---

### 4.2 Dashboard（工作台首页）

**顶部统计卡片：**
- 进行中任务数
- 今日完成任务数
- 本月已用 image credits / video credits
- 生成资源总数

**实时图表（Recharts）：**
- 近 7 天任务量趋势（折线图）
- 输出类型分布（饼图：main_image / video / lifestyle 等）
- 模型使用分布（柱状图）

> 注：Dashboard 数据来自后端已有接口组合：`GET /api/v1/tasks/{job_id}` 循环查询、JobStore 查询。若数据不足，图表可降级为占位数据并标注“演示数据”。

**最近任务列表：**
- 表格展示 job_id、状态、SKU 数、完成数、创建时间
- 点击跳转 Task Detail

---

### 4.3 Batch Submit（批量提交）

**表单结构：**
- 任务级配置：
  - `image_model`：fast / pro
  - `video_model`：veo / seedance
- SKU 列表（可动态增删行），每行字段：
  - `sku_id`（必填）
  - `product_image_url`（文本输入）
  - `product_name`
  - `category`
  - `target_platforms`：多选（amazon / tiktok / instagram / etc.）
  - `output_types`：多选（main_image / video / lifestyle）
  - `market`：US / CN / JP / etc.
  - `style_hint`（可选）

**图片上传交互：**
- 每行 SKU 提供“本地上传”按钮。
- 选择文件后，调用 `POST /api/v1/upload`（新增）。
- 上传成功后，后端返回 URL，前端自动回填到 `product_image_url` 字段。
- 上传期间显示进度条/loading。

**提交后：**
- 显示 job_id
- 跳转 Task Detail 页

---

### 4.4 Task Detail（任务详情）

**状态区：**
- 当前状态：pending / running / completed / failed
- 进度条：`done_skus / total_skus`
- 创建时间、耗时

**SSE 实时流：**
- 连接 `GET /api/v1/tasks/{job_id}/stream`
- 解析 `event: progress` 事件，更新进度与日志
- 收到 `event: done` 后自动刷新一次完整任务数据

**结果画廊：**
- 按 SKU 分组展示生成的图片/视频
- 图片支持点击放大、复制 URL
- 视频支持播放
- 失败任务显示错误原因

---

### 4.5 Agent Chat（AI 助手）

**界面：**
- 左侧会话列表（最近会话）
- 右侧聊天区
- 底部输入框 + 快捷提示词按钮

**SSE 流式回复：**
- 连接 `POST /api/v1/agent/chat`
- 解析 `data:` 消息块，逐字渲染
- 收到 `data: [DONE]` 结束流

**快捷提示词：**
- “生成一张亚马逊主图”
- “帮我检查这个提示词是否合规”
- “推荐几个爆款参考”

---

## 5. 后端需要补充的接口

### 5.1 `GET /api/v1/me`

返回当前 API Key 对应的租户信息：

```json
{
  "tenant_id": "tenant-001",
  "name": "Demo Pro",
  "plan": "pro",
  "quotas": {
    "max_concurrent_jobs": 5,
    "max_skus_per_job": 500,
    "image_credits_monthly": 1000,
    "video_credits_monthly": 100
  }
}
```

### 5.2 `POST /api/v1/upload`

接收 multipart 文件，保存到 `outputs/uploads/{tenant_id}/{uuid}.{ext}`，返回可访问 URL：

```json
{
  "url": "/outputs/uploads/tenant-001/xxx.jpg"
}
```

同时 gateway 需要挂载静态文件：`/outputs` -> `outputs/`。

---

## 6. 组件清单

| 组件 | 用途 |
|------|------|
| `Sidebar` | 左侧导航 |
| `Topbar` | 顶部租户与操作 |
| `StatCard` | Dashboard 统计卡片 |
| `JobChart` | Recharts 图表封装 |
| `JobTable` | 最近任务列表 |
| `SkuForm` | SKU 行表单（含上传） |
| `SkuList` | 动态 SKU 列表管理 |
| `TaskProgress` | 状态/进度/SSE 日志 |
| `AssetGallery` | 生成资源画廊 |
| `ChatWindow` | Agent 聊天窗口 |
| `ApiKeyInput` | API Key 输入与校验 |
| `TenantCard` | 租户/Plan 展示卡片 |

---

## 7. 路由结构

| 路径 | 页面 |
|------|------|
| `/login` | Login / Tenant 选择 |
| `/dashboard` | Dashboard |
| `/batch` | Batch Submit |
| `/tasks/[jobId]` | Task Detail |
| `/agent` | Agent Chat |

---

## 8. 关键实现细节

### 8.1 SSE with Authorization

原生 `EventSource` 不能带 `X-Api-Key`，因此使用：

```ts
const res = await fetch(`/api/v1/tasks/${jobId}/stream`, {
  headers: { "X-Api-Key": apiKey },
});
const reader = res.body?.getReader();
// 解析 text/event-stream
```

### 8.2 文件上传回填

```ts
const file = ...;
const formData = new FormData();
formData.append("file", file);
const { url } = await api.post("/upload", formData);
setFieldValue(`skus[${index}].product_image_url`, url);
```

### 8.3 认证守卫

- 未登录访问 `/dashboard`、`/batch` 等页面，中间件自动重定向 `/login`。
- `/login` 已登录则重定向 `/dashboard`。

---

## 9. 测试策略

1. **组件测试**：`StatCard`、`TenantCard`、`SkuForm` 渲染与交互。
2. **Hook 测试**：`useSse`、`useUpload` 的 mock 测试。
3. **E2E（可选）**：登录 → 提交批量任务 → 查看详情（需要后端运行）。

---

## 10. 交付标准

- `npm run build` 成功生成 `dist/`。
- 所有页面可路由访问。
- 登录后可查看 Tenant/Plan。
- 批量提交支持 URL 和本地上传回填。
- Task Detail 可 SSE 实时查看进度。
- Agent Chat 可流式对话。
- 新增后端接口有对应测试。
