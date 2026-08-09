'use client'

import { type ClipboardEvent, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Bot,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  History,
  Loader2,
  MessageSquare,
  ListChecks,
  Paperclip,
  Plus,
  Search,
  Send,
  Trash2,
  ThumbsDown,
  ThumbsUp,
  User,
  WandSparkles,
  Wrench,
  X,
} from 'lucide-react'

import { api } from '@/lib/api'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  ReferenceProductPicker,
  type ReferenceProduct,
} from '@/components/ReferenceProductPicker'
import type { JobDetail, JobStatus } from '@/types/job'
import { PLATFORM_OPTIONS } from '@/lib/sku-options'
import { useModels } from '@/hooks/useModels'

type MessageContextImage = {
  url: string
  label: string
  source: 'product' | 'upload'
}

export type Message = {
  role: 'user' | 'assistant'
  content: string
  taskId?: string
  confirmation?: AgentConfirmation
  traceId?: string
  referenceResult?: AgentReferenceResult
  qualityResult?: AgentQualityResult
  toolFailure?: AgentToolFailure
  contextImages?: MessageContextImage[]
  contextImageUrl?: string
  contextLabel?: string
  contextSource?: 'product' | 'upload'
}

type AgentReferenceItem = {
  product_id: string
  score: number
  image_url: string
  category?: string
  style?: string
  color?: string
  material?: string
}

type AgentReferenceResult = {
  ok: boolean
  matched?: boolean
  message?: string
  score_type?: string
  results?: AgentReferenceItem[]
}

type AgentQualityResult = {
  compliant: boolean
  product_visible: boolean
  background_compliant: boolean
  has_prohibited_overlay: boolean
  issues?: string[]
  summary: string
}

type AgentToolFailure = {
  code?: string
  message?: string
  retryable?: boolean
}

type AgentConfirmation = {
  confirmation_id: string
  expires_in: number
  summary: {
    sku_id: string
    product_name: string
    platforms: string[]
    output_types: string[]
    image_model: string
    image_size: string
    aspect_ratio: string
    presentation_mode?: 'auto' | 'model_wear' | 'product_only'
    model_preference?: 'auto' | 'female' | 'male' | 'no_face'
    style_hint?: string | null
    reference_mode?: 'auto' | 'specified' | 'none'
    ref_sku_id?: string | null
  }
}

type ChatSession = { id: string; title: string }
type AgentSessionDto = { session_id: string; title: string }
type AgentSessionContext = {
  uploaded_product?: { image_url?: string; image_name?: string }
  selected_product?: Partial<ReferenceProduct> & { sku_code?: string; image_url?: string }
  target_platform?: string
}

const WELCOME: Message = {
  role: 'assistant',
  content: '上传新品图后，我可以帮你查找爆款参考、准备主图或详情图，并检查和修复生成结果。',
}

type QuickAction = {
  label: string
  hint: string
  prompt: string
  icon: typeof Search
  requiresSource?: boolean
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: '查找爆款参考', hint: '用新品图匹配相似商品', prompt: '通过新品图查找相似爆款参考', icon: Search, requiresSource: true },
  { label: '生成商品图', hint: '准备主图或详情图任务', prompt: '为新品生成电商商品图', icon: WandSparkles },
  { label: '检查并修复', hint: '分析失败原因和质量问题', prompt: '检查并修复生成结果', icon: Wrench },
  { label: '查询当前任务', hint: '输入任务编号查看进度', prompt: '查询指定任务的状态', icon: ListChecks },
]

const TOOL_LABELS: Record<string, string> = {
  rag_search: '正在检索爆款参考',
  check_image_compliance: '正在检查图片质量',
  submit_generation_job: '正在准备任务配置',
  get_generation_job: '正在查询任务结果',
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: '等待中',
  running: '生成中',
  done: '已完成',
  partial_fail: '部分失败',
  failed: '失败',
}

const OUTPUT_TYPE_OPTIONS = [
  { value: 'main_image', label: '主图' },
  { value: 'detail_page', label: '详情图（3张）' },
  { value: 'pdd_white_background', label: '拼多多白底图' },
]

const PRESENTATION_OPTIONS = [
  { value: 'auto', label: '智能判断' },
  { value: 'model_wear', label: '模特上身' },
  { value: 'product_only', label: '仅展示商品' },
]

const MODEL_PREFERENCE_OPTIONS = [
  { value: 'auto', label: '自动选择' },
  { value: 'female', label: '女模' },
  { value: 'male', label: '男模' },
  { value: 'no_face', label: '不露脸' },
]

const ASPECT_RATIO_OPTIONS = ['auto', '1:1', '3:4', '4:5', '9:16', '16:9']
const IMAGE_SIZE_OPTIONS = ['1K', '2K', '4K']

function extractTaskId(content: string): string | null {
  return content.match(/(?:jobId=|job[_ ]?id[：:=\s]+|任务\s*(?:ID|id)?[：:\s]+)([0-9a-f-]{36})/i)?.[1] ?? null
}

function TaskResultCard({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const load = async () => {
      try {
        const data = await api.get<JobDetail>(`/v1/tasks/${jobId}`)
        if (stopped) return
        setJob(data)
        setError(null)
        if (!['done', 'failed', 'partial_fail'].includes(data.status)) {
          timer = setTimeout(load, 5000)
        }
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : '任务加载失败')
      }
    }

    load()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [jobId])

  const images = job?.assets.filter((asset) => asset.status === 'success' && asset.file_path) ?? []
  const failures = job?.job_items.filter((item) => item.error_msg) ?? []

  return (
    <div className="mt-3 w-full min-w-[280px] rounded-lg border bg-background p-3 text-foreground shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium">生成任务</p>
          <p className="truncate font-mono text-[10px] text-muted-foreground">{jobId}</p>
        </div>
        <div className="flex items-center gap-2">
          {job ? <Badge variant="outline">{STATUS_LABELS[job.status]}</Badge> : <Loader2 className="h-4 w-4 animate-spin" />}
          <Button variant="ghost" size="sm" className="h-7 px-2" asChild>
            <Link href={`/tasks?jobId=${jobId}`}>
              详情<ExternalLink className="ml-1 h-3 w-3" />
            </Link>
          </Button>
        </div>
      </div>
      {job && (
        <p className="mt-2 text-xs text-muted-foreground">
          已处理 {job.done_skus}/{job.total_skus} 个 SKU · 成功图片 {images.length} 张
        </p>
      )}
      {images.length > 0 && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {images.slice(0, 6).map((asset) => (
            <Dialog key={asset.asset_id}>
              <DialogTrigger asChild>
                <button type="button" className="aspect-square overflow-hidden rounded-md border bg-muted">
                  <img src={asset.file_path!} alt={asset.output_type} className="h-full w-full object-cover" />
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-4xl">
                <DialogHeader><DialogTitle>{asset.sku_id} · {asset.output_type}</DialogTitle></DialogHeader>
                <img src={asset.file_path!} alt={asset.output_type} className="mx-auto max-h-[75vh] rounded-md" />
              </DialogContent>
            </Dialog>
          ))}
        </div>
      )}
      {(error || failures.length > 0) && (
        <p className="mt-2 text-xs text-destructive">
          {error || failures[0]?.error_msg}
        </p>
      )}
    </div>
  )
}

function ConfirmationCard({
  confirmation,
  onConfirmed,
  productImageUrl,
  referenceImageUrl,
}: {
  confirmation: AgentConfirmation
  onConfirmed: (jobId: string) => void
  productImageUrl?: string
  referenceImageUrl?: string
}) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const summary = confirmation.summary
  const { imageModels } = useModels()
  const [platform, setPlatform] = useState(summary.platforms[0] || '')
  const [outputTypes, setOutputTypes] = useState(summary.output_types)
  const [presentationMode, setPresentationMode] = useState<string>(summary.presentation_mode || 'auto')
  const [modelPreference, setModelPreference] = useState<string>(summary.model_preference || 'auto')
  const [styleHint, setStyleHint] = useState(summary.style_hint || '')
  const [imageModel, setImageModel] = useState(summary.image_model)
  const [aspectRatio, setAspectRatio] = useState(summary.aspect_ratio)
  const [imageSize, setImageSize] = useState(summary.image_size)
  const [useReference, setUseReference] = useState(summary.reference_mode !== 'none' && Boolean(summary.ref_sku_id || referenceImageUrl))

  const changePlatform = (value: string) => {
    setPlatform(value)
    if (value !== 'pinduoduo') {
      setOutputTypes((current) => current.filter((item) => item !== 'pdd_white_background'))
    }
  }

  const toggleOutputType = (value: string) => {
    if (value === 'pdd_white_background' && platform !== 'pinduoduo') return
    setOutputTypes((current) => current.includes(value)
      ? current.length > 1 ? current.filter((item) => item !== value) : current
      : [...current, value])
  }

  const confirm = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const result = await api.post<{ job_id: string }>(
        '/v1/agent/confirm',
        {
          confirmation_id: confirmation.confirmation_id,
          target_platforms: [platform],
          output_types: outputTypes,
          presentation_mode: presentationMode,
          model_preference: presentationMode === 'product_only' ? 'auto' : modelPreference,
          style_hint: styleHint,
          image_model: imageModel,
          aspect_ratio: aspectRatio,
          image_size: imageSize,
          reference_mode: useReference ? 'specified' : 'none',
        },
      )
      onConfirmed(result.job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '任务确认失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mt-3 rounded-lg border bg-background p-3 text-foreground shadow-sm">
      <div className="flex items-center justify-between gap-2"><p className="text-sm font-medium">确认生成任务</p><Badge variant="outline">提交前确认</Badge></div>
      <div className="mt-3 grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
        <div className="grid grid-cols-2 gap-2">
          <div className="overflow-hidden rounded-md border bg-muted/30"><div className="aspect-square">{productImageUrl ? <img src={productImageUrl} alt="新品原图" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground">新品图</div>}</div><p className="border-t px-2 py-1 text-[10px] text-muted-foreground">新品原图</p></div>
          <div className="overflow-hidden rounded-md border bg-muted/30"><div className="aspect-square">{referenceImageUrl ? <img src={referenceImageUrl} alt="爆款参考" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center px-2 text-center text-[10px] text-muted-foreground">无指定参考</div>}</div><p className="border-t px-2 py-1 text-[10px] text-muted-foreground">爆款参考</p></div>
          {referenceImageUrl && (
            <button type="button" onClick={() => setUseReference((current) => !current)} className={`col-span-2 rounded-md border px-2 py-1.5 text-[11px] ${useReference ? 'border-primary bg-primary/10 text-primary' : 'bg-background text-muted-foreground'}`}>
              {useReference ? `使用爆款参考${summary.ref_sku_id ? ` · ${summary.ref_sku_id}` : ''}` : '本次不使用爆款参考'}
            </button>
          )}
        </div>
        <div className="grid content-start gap-2 text-xs sm:grid-cols-2">
          <span className="rounded-md bg-muted/30 px-2.5 py-2"><span className="block text-[10px] text-muted-foreground">商品</span>{summary.product_name || summary.sku_id}</span>
          <span className="rounded-md bg-muted/30 px-2.5 py-2"><span className="block text-[10px] text-muted-foreground">尺寸与模型</span>{summary.image_size} · {summary.aspect_ratio} · {summary.image_model}</span>
          <label className="rounded-md bg-muted/30 px-2.5 py-2 sm:col-span-2">
            <span className="mb-1 block text-[10px] text-muted-foreground">目标平台（提交前可修改）</span>
            <Select value={platform} onValueChange={changePlatform}>
              <SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>{PLATFORM_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <div className="rounded-md bg-muted/30 px-2.5 py-2 sm:col-span-2">
            <span className="mb-1.5 block text-[10px] text-muted-foreground">输出类型（可多选）</span>
            <div className="flex flex-wrap gap-1.5">
              {OUTPUT_TYPE_OPTIONS.map((option) => {
                const selected = outputTypes.includes(option.value)
                const disabled = option.value === 'pdd_white_background' && platform !== 'pinduoduo'
                return <button key={option.value} type="button" disabled={disabled} onClick={() => toggleOutputType(option.value)} className={`rounded-md border px-2.5 py-1.5 text-[11px] transition-colors ${selected ? 'border-primary bg-primary/10 text-primary' : 'bg-background text-muted-foreground'} disabled:cursor-not-allowed disabled:opacity-40`}>{option.label}</button>
              })}
            </div>
          </div>
          <label className="rounded-md bg-muted/30 px-2.5 py-2">
            <span className="mb-1 block text-[10px] text-muted-foreground">商品展示方式</span>
            <Select value={presentationMode} onValueChange={setPresentationMode}>
              <SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>{PRESENTATION_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="rounded-md bg-muted/30 px-2.5 py-2">
            <span className="mb-1 block text-[10px] text-muted-foreground">模特偏好</span>
            <Select value={modelPreference} onValueChange={setModelPreference} disabled={presentationMode === 'product_only'}>
              <SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>{MODEL_PREFERENCE_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="rounded-md bg-muted/30 px-2.5 py-2">
            <span className="mb-1 block text-[10px] text-muted-foreground">图片模型</span>
            <Select value={imageModel} onValueChange={setImageModel}>
              <SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>{imageModels.map((option) => <SelectItem key={option.alias} value={option.alias}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <div className="grid grid-cols-2 gap-2 rounded-md bg-muted/30 px-2.5 py-2">
            <label><span className="mb-1 block text-[10px] text-muted-foreground">宽高比</span><Select value={aspectRatio} onValueChange={setAspectRatio}><SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger><SelectContent>{ASPECT_RATIO_OPTIONS.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent></Select></label>
            <label><span className="mb-1 block text-[10px] text-muted-foreground">质量档位</span><Select value={imageSize} onValueChange={setImageSize}><SelectTrigger className="h-8 bg-background"><SelectValue /></SelectTrigger><SelectContent>{IMAGE_SIZE_OPTIONS.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent></Select></label>
          </div>
          <label className="rounded-md bg-muted/30 px-2.5 py-2 sm:col-span-2">
            <span className="mb-1 block text-[10px] text-muted-foreground">场景与风格</span>
            <Textarea value={styleHint} onChange={(event) => setStyleHint(event.target.value)} maxLength={500} placeholder="例如：明亮摄影棚、自然站姿、柔和日光、突出面料垂坠" className="min-h-16 resize-none bg-background text-xs" />
          </label>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2"><Button className="h-8" size="sm" onClick={confirm} disabled={submitting}>
        {submitting && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
        确认并提交
      </Button><span className="text-[10px] text-muted-foreground">平台和输出类型以当前卡片选择为准</span></div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  )
}

function ReferenceResultCard({
  result,
  onSelect,
  onContinueWithoutReference,
}: {
  result: AgentReferenceResult
  onSelect: (product: ReferenceProduct) => void
  onContinueWithoutReference: () => void
}) {
  const references = result.results || []
  if (!result.matched || references.length === 0) {
    return (
      <div className="mt-3 rounded-lg border border-dashed bg-background p-3 text-foreground">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">没有找到可靠的爆款参考</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{result.message || '可以补充品类、版型、颜色等条件，也可以直接使用无参考图模式。'}</p>
            <Button variant="outline" size="sm" className="mt-2 h-8" onClick={onContinueWithoutReference}>无参考图继续生成</Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-lg border bg-background p-3 text-foreground shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">找到 {references.length} 个爆款参考</p>
          <p className="text-[10px] text-muted-foreground">按图文相似度排序，选择后将用于本次生成</p>
        </div>
        <Badge variant="outline">可信匹配</Badge>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {references.slice(0, 3).map((reference) => (
          <div key={reference.product_id} className="min-w-0 overflow-hidden rounded-md border bg-muted/20">
            <Dialog>
              <DialogTrigger asChild>
                <button type="button" className="block aspect-square w-full overflow-hidden bg-muted">
                  <img src={reference.image_url} alt={reference.product_id} className="h-full w-full object-cover" loading="lazy" />
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-4xl">
                <DialogHeader><DialogTitle>{reference.product_id}</DialogTitle></DialogHeader>
                <img src={reference.image_url} alt={reference.product_id} className="mx-auto max-h-[75vh] rounded-md object-contain" />
              </DialogContent>
            </Dialog>
            <div className="p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium">{reference.product_id}</span>
                <span className="text-[10px] font-medium text-primary">{Math.round(reference.score * 100)}%</span>
              </div>
              <p className="mt-1 truncate text-[10px] text-muted-foreground">
                {[reference.category, reference.color, reference.style].filter(Boolean).join(' · ') || '商品参考'}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 w-full text-[11px]"
                onClick={() => onSelect({
                  sku_code: reference.product_id,
                  category: reference.category || 'apparel',
                  description: [reference.style, reference.color, reference.material].filter(Boolean).join(' '),
                  image_url: reference.image_url,
                  sales_count: 0,
                })}
              >
                设为爆款参考
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function QualityResultCard({ result, onRepair, productImageUrl, referenceImageUrl }: { result: AgentQualityResult; onRepair: () => void; productImageUrl?: string; referenceImageUrl?: string }) {
  const checks = [
    ['商品展示', result.product_visible],
    ['背景规则', result.background_compliant],
    ['无违规覆盖元素', !result.has_prohibited_overlay],
  ] as const
  return (
    <div className={`mt-3 rounded-lg border bg-background p-3 text-foreground shadow-sm ${result.compliant ? 'border-emerald-500/30' : 'border-amber-500/40'}`}>
      <div className="flex items-start gap-2">
        {result.compliant
          ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{result.compliant ? '图片检查通过' : '发现需要修复的问题'}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{result.summary}</p>
        </div>
      </div>
      {(productImageUrl || referenceImageUrl) && <div className="mt-3 grid max-w-sm grid-cols-2 gap-2">
        {productImageUrl && <div className="overflow-hidden rounded-md border bg-muted/20"><img src={productImageUrl} alt="新品原图" className="aspect-square w-full object-cover" /><p className="border-t px-2 py-1 text-[10px] text-muted-foreground">新品原图</p></div>}
        {referenceImageUrl && <div className="overflow-hidden rounded-md border bg-muted/20"><img src={referenceImageUrl} alt="爆款参考" className="aspect-square w-full object-cover" /><p className="border-t px-2 py-1 text-[10px] text-muted-foreground">爆款参考</p></div>}
      </div>}
      <div className="mt-3 grid grid-cols-3 gap-1.5">
        {checks.map(([label, passed]) => (
          <div key={label} className={`rounded-md px-2 py-1.5 text-center text-[10px] ${passed ? 'bg-emerald-500/10 text-emerald-700' : 'bg-amber-500/10 text-amber-700'}`}>
            {passed ? '通过' : '需调整'} · {label}
          </div>
        ))}
      </div>
      {Boolean(result.issues?.length) && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          {result.issues!.map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      )}
      {!result.compliant && <Button variant="outline" size="sm" className="mt-3 h-8" onClick={onRepair}>按检查结果准备重生成</Button>}
    </div>
  )
}

function ToolFailureCard({ failure, onRetry }: { failure: AgentToolFailure; onRetry: () => void }) {
  return (
    <div className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-foreground">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">本次操作未完成</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{failure.message || '业务工具暂时不可用。'}</p>
        {failure.retryable && <Button variant="outline" size="sm" className="mt-2 h-8" onClick={onRetry}>重新尝试</Button>}
      </div>
    </div>
  )
}

function ResponseFeedback({ traceId, sessionId }: { traceId: string; sessionId: string }) {
  const [rating, setRating] = useState<'helpful' | 'unhelpful' | null>(null)
  const submit = async (next: 'helpful' | 'unhelpful') => {
    if (rating) return
    try {
      await api.post('/v1/agent/feedback', { trace_id: traceId, session_id: sessionId, rating: next })
      setRating(next)
    } catch { /* feedback must not interrupt the workflow */ }
  }
  return (
    <div className="mt-2 flex items-center gap-1 text-[10px] text-muted-foreground">
      <span className="mr-1">这个结果有用吗？</span>
      <button type="button" className={`rounded p-1 hover:bg-background ${rating === 'helpful' ? 'text-primary' : ''}`} onClick={() => submit('helpful')} aria-label="有用"><ThumbsUp className="h-3.5 w-3.5" /></button>
      <button type="button" className={`rounded p-1 hover:bg-background ${rating === 'unhelpful' ? 'text-destructive' : ''}`} onClick={() => submit('unhelpful')} aria-label="没用"><ThumbsDown className="h-3.5 w-3.5" /></button>
      {rating && <span>已记录</span>}
    </div>
  )
}

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0">{children}</h3>,
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-muted-foreground">{children}</blockquote>
  ),
  a: ({ href, children }) => {
    const external = Boolean(href && /^https?:\/\//i.test(href))
    return (
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className="font-medium text-primary underline decoration-primary/30 underline-offset-2 hover:decoration-primary"
      >
        {children}
      </a>
    )
  },
  code: ({ className, children }) => (
    <code className={`${className || ''} rounded bg-background/70 px-1 py-0.5 font-mono text-[0.86em]`}>{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 max-w-full overflow-x-auto rounded-lg border bg-background/80 p-3 font-mono text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 max-w-full overflow-x-auto rounded-lg border bg-background/60">
      <table className="w-full min-w-[420px] border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/70">{children}</thead>,
  th: ({ children }) => <th className="border-b px-3 py-2 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b px-3 py-2 align-top last:border-b-0">{children}</td>,
  hr: () => <hr className="my-3 border-border/70" />,
  img: ({ src, alt }) => typeof src === 'string' ? (
    <Dialog>
      <DialogTrigger asChild>
        <button type="button" className="my-2 block cursor-zoom-in overflow-hidden rounded-lg border bg-background">
          <img src={src} alt={alt || '助手图片'} className="max-h-72 max-w-full object-contain" loading="lazy" />
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl">
        <DialogHeader><DialogTitle>{alt || '图片预览'}</DialogTitle></DialogHeader>
        <img src={src} alt={alt || '助手图片'} className="mx-auto max-h-[75vh] rounded-md" />
      </DialogContent>
    </Dialog>
  ) : null,
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="min-w-0 break-words leading-6">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

function MessageContent({
  message,
  onConfirmed,
  onUseReference,
  onSuggestedPrompt,
  sessionId,
  productImageUrl,
  referenceImageUrl,
}: {
  message: Message
  onConfirmed: (jobId: string) => void
  onUseReference: (product: ReferenceProduct) => void
  onSuggestedPrompt: (prompt: string) => void
  sessionId: string
  productImageUrl?: string
  referenceImageUrl?: string
}) {
  const contextImages: MessageContextImage[] = message.contextImages?.length
    ? message.contextImages
    : message.contextImageUrl
      ? [{
          url: message.contextImageUrl,
          label: message.contextLabel || '商品图',
          source: message.contextSource || 'upload',
        }]
      : []
  const segments: { type: 'text' | 'image'; value: string }[] = []
  const referenceSummary = message.referenceResult
    ? message.referenceResult.matched && message.referenceResult.results?.length
      ? `已找到 ${message.referenceResult.results.length} 个可信爆款参考，请从下方选择一个作为生成参考。`
      : message.referenceResult.message || '没有找到达到可信阈值的爆款参考，可以补充检索条件后重试。'
    : null
  const normalized = (referenceSummary || message.content).replace(/IMAGE_GENERATED\s+((?:https?:\/\/|\/)[^\s]+)/gi, '$1')
  const parts = normalized.split(/((?:https?:\/\/|\/)[^\s"'\n]+\.(?:png|jpg|jpeg|webp))/gi)
  for (const part of parts) {
    if (part.match(/^(?:https?:\/\/|\/).+\.(?:png|jpg|jpeg|webp)$/i)) {
      segments.push({ type: 'image', value: part })
    } else if (part) {
      segments.push({ type: 'text', value: part })
    }
  }
  const taskId = message.taskId || extractTaskId(message.content)

  return (
    <div className="space-y-2">
      {contextImages.length > 0 && (
        <div className="grid w-full max-w-md grid-cols-2 gap-2">
          {contextImages.map((contextImage) => (
            <Dialog key={`${contextImage.source}:${contextImage.url}`}>
              <DialogTrigger asChild>
                <button
                  type="button"
                  className="group flex min-w-0 cursor-zoom-in items-center gap-2 rounded-lg border border-white/25 bg-background/95 p-1.5 text-left text-foreground shadow-sm"
                >
                  <img
                    src={contextImage.url}
                    alt={contextImage.label}
                    className="h-14 w-14 shrink-0 rounded-md border object-cover"
                    loading="lazy"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[10px] font-medium text-muted-foreground">
                      {contextImage.source === 'product' ? '爆款参考' : '新品原图'}
                    </span>
                    <span className="mt-0.5 block truncate text-xs font-medium">{contextImage.label}</span>
                    <span className="mt-1 block text-[10px] text-muted-foreground group-hover:text-foreground">点击查看大图</span>
                  </span>
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-4xl">
                <DialogHeader><DialogTitle>{contextImage.label}</DialogTitle></DialogHeader>
                <img src={contextImage.url} alt={contextImage.label} className="mx-auto max-h-[75vh] rounded-md object-contain" />
              </DialogContent>
            </Dialog>
          ))}
        </div>
      )}
      {segments.map((segment, index) => segment.type === 'image' ? (
        <Dialog key={index}>
          <DialogTrigger asChild>
            <button type="button" className="block cursor-zoom-in">
              <img src={segment.value} alt="生成的图片" className="max-w-xs rounded-lg border shadow-sm" loading="lazy" />
            </button>
          </DialogTrigger>
          <DialogContent className="max-w-4xl">
            <DialogHeader><DialogTitle className="font-mono text-xs break-all">{segment.value}</DialogTitle></DialogHeader>
            <img src={segment.value} alt="生成的图片" className="mx-auto max-h-[75vh] rounded-md" />
          </DialogContent>
        </Dialog>
      ) : (
        <MarkdownContent key={index} content={segment.value} />
      ))}
      {taskId && <TaskResultCard jobId={taskId} />}
      {message.confirmation && !taskId && (
        <ConfirmationCard confirmation={message.confirmation} onConfirmed={onConfirmed} productImageUrl={productImageUrl} referenceImageUrl={referenceImageUrl} />
      )}
      {message.referenceResult && (
        <ReferenceResultCard
          result={message.referenceResult}
          onSelect={onUseReference}
          onContinueWithoutReference={() => onSuggestedPrompt('不使用爆款参考图，为当前新品生成电商商品图')}
        />
      )}
      {message.qualityResult && (
        <QualityResultCard
          result={message.qualityResult}
          productImageUrl={productImageUrl}
          referenceImageUrl={referenceImageUrl}
          onRepair={() => onSuggestedPrompt(`根据刚才的质量检查问题修复并重新生成：${message.qualityResult?.issues?.join('；') || message.qualityResult?.summary}`)}
        />
      )}
      {message.toolFailure && <ToolFailureCard failure={message.toolFailure} onRetry={() => onSuggestedPrompt('重新执行刚才的操作')} />}
      {message.role === 'assistant' && message.traceId && <ResponseFeedback traceId={message.traceId} sessionId={sessionId} />}
    </div>
  )
}

export function ChatWindow() {
  const { tenant, user } = useAuth()
  const storageKey = `mediaforge-chat-sessions:${user?.user_id || 'anonymous'}`
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const cleanupRef = useRef<(() => void) | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [toolStatus, setToolStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<ReferenceProduct | null>(null)
  const [uploadedImage, setUploadedImage] = useState<string | null>(null)
  const [uploadedImageName, setUploadedImageName] = useState<string | null>(null)
  const [targetPlatform, setTargetPlatform] = useState('')
  const [uploading, setUploading] = useState(false)
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false)
  const [sessionBusy, setSessionBusy] = useState(false)

  useEffect(() => {
    if (!user) return
    let cancelled = false

    const loadSessions = async () => {
      setSessionBusy(true)
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || '[]') as ChatSession[]
        for (const session of stored) {
          await api.post<AgentSessionDto>('/v1/agent/sessions', {
            session_id: session.id,
            title: session.title,
          })
        }
        if (stored.length) localStorage.removeItem(storageKey)

        let response = await api.get<{ sessions: AgentSessionDto[] }>('/v1/agent/sessions')
        if (response.sessions.length === 0) {
          const created = await api.post<AgentSessionDto>('/v1/agent/sessions', { title: '新对话' })
          response = { sessions: [created] }
        }
        if (!cancelled) {
          const next = response.sessions.map((session) => ({ id: session.session_id, title: session.title }))
          setSessions(next)
          setSessionId(next[0].id)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载对话列表失败')
      } finally {
        if (!cancelled) setSessionBusy(false)
      }
    }

    loadSessions()
    return () => { cancelled = true }
  }, [storageKey, user])

  useEffect(() => {
    if (!tenant || !user || !sessionId) return
    let cancelled = false
    setHistoryLoaded(false)
    setMessages([WELCOME])
    api.get<{ messages: Message[]; context?: AgentSessionContext }>(`/v1/agent/history?session_id=${sessionId}`)
      .then((response) => {
        if (cancelled) return
        if (response.messages?.length) setMessages([WELCOME, ...response.messages])
        const uploaded = response.context?.uploaded_product
        setUploadedImage(uploaded?.image_url || null)
        setUploadedImageName(uploaded?.image_name || null)
        const selected = response.context?.selected_product
        setSelectedProduct(selected?.sku_code && selected.image_url ? {
          sku_code: selected.sku_code,
          image_url: selected.image_url,
          category: selected.category || 'apparel',
          description: selected.description || '',
          sales_count: selected.sales_count || 0,
        } : null)
        setTargetPlatform(response.context?.target_platform || '')
      })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setHistoryLoaded(true) })
    return () => { cancelled = true }
  }, [tenant, user, sessionId])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, toolStatus])

  useEffect(() => {
    if (isStreaming) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((value) => value + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isStreaming])

  useEffect(() => () => cleanupRef.current?.(), [])

  const selectSession = (targetSessionId: string) => {
    if (isStreaming || targetSessionId === sessionId) return
    setSessionId(targetSessionId)
    setSessionMenuOpen(false)
    setSelectedProduct(null)
    setUploadedImage(null)
    setUploadedImageName(null)
    setTargetPlatform('')
    setError(null)
  }

  const createSession = async () => {
    if (isStreaming || sessionBusy) return
    setSessionBusy(true)
    setError(null)
    try {
      const created = await api.post<AgentSessionDto>('/v1/agent/sessions', { title: '新对话' })
      const next = { id: created.session_id, title: created.title }
      setSessions((current) => [next, ...current.filter((session) => session.id !== next.id)])
      setSessionId(next.id)
      setSessionMenuOpen(false)
      setSelectedProduct(null)
      setUploadedImage(null)
      setUploadedImageName(null)
      setTargetPlatform('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '新建对话失败')
    } finally {
      setSessionBusy(false)
    }
  }

  const deleteSession = async (targetSessionId: string) => {
    if (isStreaming || sessionBusy) return
    setSessionBusy(true)
    setError(null)
    try {
      await api.delete(`/v1/agent/sessions/${targetSessionId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除对话失败')
      setSessionBusy(false)
      return
    }

    const remaining = sessions.filter((session) => session.id !== targetSessionId)
    if (remaining.length === 0) {
      try {
        const created = await api.post<AgentSessionDto>('/v1/agent/sessions', { title: '新对话' })
        const replacement = { id: created.session_id, title: created.title }
        setSessions([replacement])
        setSessionId(replacement.id)
      } catch (err) {
        setSessions([])
        setSessionId('')
        setError(err instanceof Error ? err.message : '创建新对话失败')
      }
    } else {
      setSessions(remaining)
      if (targetSessionId === sessionId) setSessionId(remaining[0].id)
    }
    if (targetSessionId === sessionId) {
      setSelectedProduct(null)
      setUploadedImage(null)
      setUploadedImageName(null)
      setTargetPlatform('')
    }
    setSessionBusy(false)
  }

  const handleUpload = async (file: File | undefined) => {
    if (!file || uploading) return
    setUploading(true)
    setError(null)
    try {
      const result = await api.upload(file)
      setUploadedImage(result.url)
      setUploadedImageName(file.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : '商品图上传失败')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const imageItem = Array.from(event.clipboardData.items).find((item) => item.type.startsWith('image/'))
    const clipboardImage = imageItem?.getAsFile()
    if (!clipboardImage) return

    event.preventDefault()
    const extension = clipboardImage.type.split('/')[1]?.replace('jpeg', 'jpg') || 'png'
    const pastedFile = new File(
      [clipboardImage],
      `clipboard-${Date.now()}.${extension}`,
      { type: clipboardImage.type },
    )
    void handleUpload(pastedFile)
  }

  const handleSubmit = () => {
    const text = input.trim()
    if (!text || isStreaming || uploading || !sessionId) return

    setInput('')
    setError(null)
    setToolStatus(null)
    const contextImages: MessageContextImage[] = []
    if (uploadedImage) {
      contextImages.push({
        url: uploadedImage,
        label: uploadedImageName || '上传商品图',
        source: 'upload',
      })
    }
    if (selectedProduct) {
      contextImages.push({
        url: selectedProduct.image_url,
        label: [selectedProduct.sku_code, selectedProduct.category].filter(Boolean).join(' · '),
        source: 'product',
      })
    }
    const messageContext: Pick<Message, 'contextImages'> = contextImages.length ? { contextImages } : {}
    setMessages((current) => [...current, { role: 'user', content: text, ...messageContext }])
    setIsStreaming(true)

    const currentSession = sessions.find((session) => session.id === sessionId)
    if (currentSession?.title === '新对话' || currentSession?.title === '默认对话') {
      setSessions((current) => current.map((session) => session.id === sessionId
        ? { ...session, title: text.slice(0, 18) }
        : session))
    }

    let assistantContent = ''
    let taskId: string | undefined
    let confirmation: AgentConfirmation | undefined
    let traceId: string | undefined
    let referenceResult: AgentReferenceResult | undefined
    let qualityResult: AgentQualityResult | undefined
    let toolFailure: AgentToolFailure | undefined
    cleanupRef.current?.()
    cleanupRef.current = api.streamSse(
      '/v1/agent/chat',
      (raw) => {
        let event: { type?: string; content?: string; name?: string; status?: string; message?: string; trace_id?: string; job?: { job_id?: string }; confirmation?: AgentConfirmation; result?: AgentReferenceResult | AgentQualityResult; failure?: AgentToolFailure; response?: { status?: string; answer?: string; evidence?: string[] } }
        try {
          event = JSON.parse(raw)
        } catch {
          event = { type: 'content', content: raw }
        }
        if (event.type === 'meta') {
          traceId = event.trace_id
        } else if (event.type === 'content' && event.content) {
          assistantContent += event.content
        } else if (event.type === 'tool') {
          setToolStatus(event.status === 'running' ? (TOOL_LABELS[event.name || ''] || '正在调用业务工具') : null)
        } else if (event.type === 'task' && event.job?.job_id) {
          taskId = event.job.job_id
        } else if (event.type === 'confirmation' && event.confirmation) {
          confirmation = event.confirmation
        } else if (event.type === 'reference_result' && event.result) {
          referenceResult = event.result as AgentReferenceResult
        } else if (event.type === 'quality_result' && event.result) {
          qualityResult = event.result as AgentQualityResult
        } else if (event.type === 'tool_failure' && event.failure) {
          toolFailure = event.failure
        } else if (event.type === 'response' && event.response?.answer) {
          assistantContent = event.response.answer
        } else if (event.type === 'error') {
          setError(`${event.message || '助手执行失败'}${event.trace_id ? `（追踪号 ${event.trace_id}）` : ''}`)
        } else if (event.type === 'done') {
          setToolStatus(null)
        }
        if (assistantContent || taskId || confirmation || referenceResult || qualityResult || toolFailure) {
          setMessages((current) => {
            const base = current[current.length - 1]?.role === 'assistant' ? current.slice(0, -1) : current
            return [...base, { role: 'assistant', content: assistantContent, taskId, confirmation, traceId, referenceResult, qualityResult, toolFailure }]
          })
        }
      },
      () => { setIsStreaming(false); setToolStatus(null) },
      (err) => { setIsStreaming(false); setToolStatus(null); setError(err.message) },
      {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          product_sku: selectedProduct?.sku_code || null,
          uploaded_image_url: uploadedImage,
          uploaded_image_name: uploadedImageName,
          target_platform: targetPlatform || null,
        }),
      },
    )
  }

  const handleClear = async () => {
    try { await api.delete(`/v1/agent/history?session_id=${sessionId}`) } catch { /* keep local clear usable */ }
    setMessages([WELCOME])
    setError(null)
  }

  const activityLabel = toolStatus || (elapsed < 5 ? '正在理解需求' : `正在处理 · ${elapsed}s`)
  const currentSessionTitle = sessions.find((session) => session.id === sessionId)?.title || '新对话'
  const currentPlatformLabel = PLATFORM_OPTIONS.find((platform) => platform.value === targetPlatform)?.label
  const latestConfirmation = [...messages].reverse().find((message) => message.confirmation)?.confirmation
  const latestTaskId = [...messages].reverse().find((message) => message.taskId)?.taskId
  const hasSource = Boolean(uploadedImage || selectedProduct)
  const hasReference = Boolean(uploadedImage && selectedProduct)
  const hasGeneration = Boolean(latestConfirmation || latestTaskId)
  const hasQualityResult = messages.some((message) => Boolean(message.qualityResult))
  const activeStage = hasQualityResult ? 4 : hasGeneration ? 3 : targetPlatform && hasSource ? 2 : hasSource ? 1 : 0
  const outputLabel = latestConfirmation?.summary.output_types?.length
    ? latestConfirmation.summary.output_types.map((type) => ({ main_image: '主图', detail_page: '详情图', pdd_white_background: '白底图' }[type] || type)).join('、')
    : '待确认'
  const workflowSteps = ['选择商品', '查找参考', '确认规则', '生成图片', '质量检查']

  const contextualActions: QuickAction[] = !hasSource
    ? [QUICK_ACTIONS[0], QUICK_ACTIONS[1]]
    : !hasReference
      ? [
          QUICK_ACTIONS[0],
          { label: '无参考生成', hint: '直接使用新品图', prompt: '不使用爆款参考图，为当前新品生成电商商品图', icon: WandSparkles },
        ]
      : !hasGeneration
        ? [
            { label: '生成主图', hint: '准备单品主图任务', prompt: '使用当前新品和爆款参考生成电商主图', icon: WandSparkles },
            { label: '生成详情图', hint: '准备详情页图片任务', prompt: '使用当前新品和爆款参考生成详情页图片', icon: WandSparkles },
          ]
        : !hasQualityResult
          ? [
              ...(latestTaskId ? [{ label: '查询当前任务', hint: '查看进度与结果', prompt: `查询任务 ${latestTaskId} 的状态`, icon: ListChecks }] : []),
              { label: '检查生成结果', hint: '检查平台合规与质量', prompt: latestTaskId ? `检查任务 ${latestTaskId} 的生成结果` : '检查当前生成结果', icon: Wrench },
            ]
          : [
              { label: '按问题重生成', hint: '使用质量建议修复', prompt: '根据刚才的质量检查问题修复并重新生成', icon: Wrench },
              { label: '生成新版本', hint: '保留当前结果并创建新版', prompt: '保留当前结果，并为当前商品生成一个新版本', icon: WandSparkles },
            ]

  const applyQuickAction = (action: QuickAction) => {
    setInput(action.prompt)
    if (action.requiresSource && !uploadedImage && !selectedProduct) {
      fileInputRef.current?.click()
    }
    requestAnimationFrame(() => textareaRef.current?.focus())
  }

  return (
    <Card className="relative flex h-full min-h-0 w-full overflow-hidden border-border/70 bg-card/80">
      {sessionMenuOpen && (
        <button
          type="button"
          className="absolute inset-0 z-20 bg-background/40 backdrop-blur-[1px]"
          onClick={() => setSessionMenuOpen(false)}
          aria-label="关闭会话菜单"
        />
      )}
      <CardContent className="flex min-h-0 min-w-0 flex-1 flex-col p-0">
        <div className="relative z-30 flex h-12 shrink-0 items-center gap-2 border-b bg-muted/10 px-2.5 sm:px-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground"><Bot className="h-4 w-4" /></span>
          <button
            type="button"
            onClick={() => setSessionMenuOpen((open) => !open)}
            className="flex min-w-0 max-w-[min(48vw,360px)] items-center gap-1.5 rounded-md px-2 py-1.5 text-left hover:bg-muted"
            aria-expanded={sessionMenuOpen}
          >
            <span className="truncate text-sm font-medium">{currentSessionTitle}</span>
            <ChevronDown className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${sessionMenuOpen ? 'rotate-180' : ''}`} />
          </button>
          {sessionMenuOpen && (
            <div className="absolute left-10 top-11 z-40 w-[min(88vw,340px)] rounded-lg border bg-popover p-2 shadow-xl">
              <Button className="mb-2 h-8 w-full justify-start" size="sm" onClick={createSession} disabled={isStreaming || sessionBusy}>
                <Plus className="mr-2 h-3.5 w-3.5" />新建对话
              </Button>
              <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">最近对话</p>
              <div className="space-y-0.5">
                {sessions.slice(0, 8).map((session) => (
                  <div key={session.id} className={`group flex items-center rounded-md ${session.id === sessionId ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
                    <button type="button" onClick={() => selectSession(session.id)} className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-xs">
                      <MessageSquare className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{session.title}</span>
                    </button>
                    <button type="button" onClick={() => deleteSession(session.id)} disabled={isStreaming || sessionBusy} className="mr-1 rounded p-1.5 opacity-60 hover:bg-destructive/10 hover:text-destructive md:opacity-0 md:group-hover:opacity-100" aria-label={`删除对话：${session.title}`}>
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
              <p className="px-2 pt-2 text-[10px] text-muted-foreground">共 {sessions.length} 个对话</p>
            </div>
          )}
          <div className="flex-1" />
          <Button variant="ghost" size="sm" className="h-8 px-2" asChild><Link href="/tasks"><History className="h-3.5 w-3.5 sm:mr-1" /><span className="hidden sm:inline">任务记录</span></Link></Button>
          <Button variant="outline" size="sm" className="h-8 px-2" onClick={createSession} disabled={isStreaming || sessionBusy}><Plus className="h-3.5 w-3.5 sm:mr-1" /><span className="hidden sm:inline">新对话</span></Button>
          <Button variant="ghost" size="sm" className="h-8 shrink-0 px-2 text-muted-foreground hover:text-destructive" onClick={handleClear} disabled={isStreaming} title="清空当前对话">
            <Trash2 className="h-3.5 w-3.5 sm:mr-1" />
            <span className="hidden sm:inline">清空</span>
          </Button>
        </div>

        <div className="shrink-0 border-b bg-background/35 px-2.5 py-2 sm:px-3">
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-[1.2fr_1.2fr_180px_140px]">
            <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background/70 p-1.5">
              {uploadedImage ? <img src={uploadedImage} alt="新品原图" className="h-9 w-9 shrink-0 rounded object-cover" /> : <button type="button" onClick={() => fileInputRef.current?.click()} className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-dashed text-muted-foreground hover:border-primary hover:text-primary"><Paperclip className="h-4 w-4" /></button>}
              <span className="min-w-0 flex-1"><span className="block text-[10px] text-muted-foreground">新品</span><span className="block truncate text-xs font-medium">{uploadedImageName || (selectedProduct ? selectedProduct.sku_code : '待上传或选择')}</span></span>
              {uploadedImage && <button type="button" className="rounded p-1 text-muted-foreground hover:text-destructive" onClick={() => { setUploadedImage(null); setUploadedImageName(null) }} aria-label="移除新品图"><X className="h-3.5 w-3.5" /></button>}
            </div>
            <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background/70 p-1.5">
              {selectedProduct && <img src={selectedProduct.image_url} alt="爆款参考" className="h-9 w-9 shrink-0 rounded object-cover" />}
              <div className="min-w-0 flex-1"><span className="mb-0.5 block text-[10px] text-muted-foreground">爆款参考</span><ReferenceProductPicker value={selectedProduct?.sku_code || ''} compact purpose="source" onSelect={setSelectedProduct} /></div>
              {selectedProduct && <button type="button" className="rounded p-1 text-muted-foreground hover:text-destructive" onClick={() => setSelectedProduct(null)} aria-label="移除爆款参考"><X className="h-3.5 w-3.5" /></button>}
            </div>
            <div className="rounded-md border bg-background/70 px-2 py-1.5">
              <span className="mb-0.5 block text-[10px] text-muted-foreground">目标平台</span>
              <Select value={targetPlatform} onValueChange={setTargetPlatform}><SelectTrigger className="h-6 border-0 bg-transparent px-0 text-xs shadow-none"><SelectValue placeholder="待选择" /></SelectTrigger><SelectContent>{PLATFORM_OPTIONS.map((platform) => <SelectItem key={platform.value} value={platform.value}>{platform.label}</SelectItem>)}</SelectContent></Select>
            </div>
            <div className="flex items-center justify-between rounded-md border bg-background/70 px-2.5 py-1.5">
              <span><span className="block text-[10px] text-muted-foreground">输出与状态</span><span className="block truncate text-xs font-medium">{outputLabel}</span></span>
              <Badge variant="outline" className="ml-2 h-5 shrink-0 px-1.5 text-[10px]">{workflowSteps[activeStage]}</Badge>
            </div>
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={(event) => handleUpload(event.target.files?.[0])} />
        </div>

        <div className="shrink-0 border-b bg-muted/5 px-3 py-2">
          <div className="mx-auto grid max-w-4xl grid-cols-5">
            {workflowSteps.map((step, index) => (
              <div key={step} className="relative flex min-w-0 flex-col items-center gap-1 text-center">
                {index > 0 && <span className={`absolute right-1/2 top-2 h-px w-full ${index <= activeStage ? 'bg-primary/70' : 'bg-border'}`} />}
                <span className={`relative z-10 flex h-4 w-4 items-center justify-center rounded-full border text-[9px] ${index < activeStage ? 'border-primary bg-primary text-primary-foreground' : index === activeStage ? 'border-primary bg-background text-primary ring-2 ring-primary/20' : 'border-border bg-background text-muted-foreground'}`}>{index < activeStage ? '✓' : index + 1}</span>
                <span className={`truncate text-[10px] ${index === activeStage ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>{step}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="scrollbar-none min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden overscroll-contain px-3 py-3 sm:px-5 sm:py-4">
          {!historyLoaded && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" />加载对话</div>}
          {messages.map((message, index) => (
            <div key={`${sessionId}-${index}`} className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
                {message.role === 'assistant' ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
              </div>
              <div className={`min-w-0 overflow-hidden text-sm ${message.role === 'user' ? 'max-w-[78%] rounded-xl bg-primary px-3 py-2.5 text-primary-foreground sm:max-w-[68%] sm:px-4' : 'w-full max-w-4xl py-1'}`}>
                <MessageContent
                  message={message}
                  sessionId={sessionId}
                  productImageUrl={uploadedImage || (!uploadedImage ? selectedProduct?.image_url : undefined)}
                  referenceImageUrl={uploadedImage ? selectedProduct?.image_url : undefined}
                  onUseReference={(product) => {
                    setSelectedProduct(product)
                    setInput('使用已选择的爆款参考，为当前新品生成电商商品图')
                    requestAnimationFrame(() => textareaRef.current?.focus())
                  }}
                  onSuggestedPrompt={(prompt) => {
                    setInput(prompt)
                    requestAnimationFrame(() => textareaRef.current?.focus())
                  }}
                  onConfirmed={(jobId) => setMessages((current) => current.map((item, itemIndex) => (
                    itemIndex === index ? { ...item, taskId: jobId, confirmation: undefined } : item
                  )))}
                />
              </div>
            </div>
          ))}
          {isStreaming && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary"><Bot className="h-4 w-4" /></div>
              <div className="flex items-center gap-2 rounded-xl bg-muted px-4 py-2.5 text-sm text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{activityLabel}</div>
            </div>
          )}
          {error && <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
          <div ref={scrollRef} />
        </div>

        <div className="shrink-0 border-t bg-background/95 p-2.5 sm:px-4 sm:py-3">
          <div className="grid min-w-0 grid-cols-[40px_minmax(0,1fr)_40px] items-end gap-2">
            <Button variant="outline" size="sm" className="h-9 w-10 px-0" disabled={uploading || isStreaming} onClick={() => fileInputRef.current?.click()} title={uploadedImage ? '更换新品图' : '上传新品图'}>{uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}<span className="sr-only">上传新品图</span></Button>
            <Textarea ref={textareaRef} value={input} onChange={(event) => setInput(event.target.value)} onPaste={handlePaste} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSubmit() } }} placeholder="描述需求，也可以在这里直接粘贴商品图片" className="min-h-9 max-h-24 resize-none" rows={1} disabled={isStreaming} />
            <Button onClick={handleSubmit} disabled={isStreaming || uploading || !input.trim()} className="h-9 w-10 px-0">{isStreaming || uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}<span className="sr-only">发送</span></Button>
          </div>
          <div className="mt-2 flex min-w-0 flex-wrap items-center gap-1.5">
            {contextualActions.map((action) => {
              const Icon = action.icon
              return <button key={action.label} type="button" onClick={() => applyQuickAction(action)} disabled={isStreaming} className="flex h-7 items-center gap-1.5 rounded-full border bg-muted/20 px-2.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50"><Icon className="h-3 w-3" />{action.label}</button>
            })}
            {currentPlatformLabel && <span className="ml-auto hidden text-[10px] text-muted-foreground sm:inline">当前平台：{currentPlatformLabel}</span>}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
