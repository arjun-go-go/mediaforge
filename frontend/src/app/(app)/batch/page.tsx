'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ImageIcon,
  ListChecks,
  Loader2,
  PackagePlus,
  Pencil,
  Copy,
  Trash2,
} from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { inferMarketFromPlatforms } from '@/lib/sku-options'
import { useModels } from '@/hooks/useModels'
import { SkuForm, type Sku } from '@/components/SkuForm'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type {
  AspectRatio,
  BatchSubmitPayload,
  ImageSize,
  JobDetail,
  SkuInput,
} from '@/types/job'

type Priority = 'low' | 'normal' | 'high'

type GenerationDraft = {
  id: string
  sku: Sku
  imageModel: string
  aspectRatio: AspectRatio
  imageSize: ImageSize
  priority: Priority
  updatedAt: number
}

const STORAGE_KEY = 'mediaforge:generation-drafts'

const createSku = (): Sku => ({
  sku_id: '',
  product_image_url: '',
  product_name: '',
  category: '',
  target_platforms: 'amazon',
  output_types: ['main_image'],
  style_hint: '',
  presentation_mode: 'auto',
  model_preference: 'auto',
  market: 'US',
  reference_mode: 'auto',
  ref_sku_id: '',
  inherits_batch_rules: false,
})

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function getSkuIssues(sku: Sku): string[] {
  const issues: string[] = []
  if (!sku.product_image_url.trim()) issues.push('缺少商品图')
  if (!sku.sku_id.trim()) issues.push('缺少 SKU 编码')
  if (!sku.product_name.trim()) issues.push('缺少商品名称')
  if (!sku.category.trim()) issues.push('缺少类目')
  if (!sku.target_platforms.trim()) issues.push('缺少平台')
  if (sku.output_types.length === 0) issues.push('缺少输出类型')
  if (sku.reference_mode === 'specified' && !sku.ref_sku_id.trim()) issues.push('未选择爆款参考')
  return issues
}

function toSkuInput(draft: GenerationDraft): SkuInput {
  const { sku } = draft
  const targetPlatforms = sku.target_platforms.split(',').map((value) => value.trim()).filter(Boolean)
  return {
    sku_id: sku.sku_id.trim(),
    product_image_url: sku.product_image_url.trim(),
    product_name: sku.product_name.trim(),
    category: sku.category.trim(),
    target_platforms: targetPlatforms,
    output_types: sku.output_types,
    style_hint: sku.style_hint.trim() || null,
    presentation_mode: sku.presentation_mode,
    model_preference: sku.model_preference,
    market: inferMarketFromPlatforms(targetPlatforms),
    aspect_ratio: draft.aspectRatio,
    image_size: draft.imageSize,
    reference_mode: sku.reference_mode,
    ref_sku_id: sku.ref_sku_id.trim() || null,
  }
}

export default function BatchPage() {
  const router = useRouter()
  const { imageModels } = useModels()
  const [sku, setSku] = useState<Sku>(createSku)
  const [imageModel, setImageModel] = useState('fast')
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('auto')
  const [imageSize, setImageSize] = useState<ImageSize>('2K')
  const [priority, setPriority] = useState<Priority>('normal')
  const [drafts, setDrafts] = useState<GenerationDraft[]>([])
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null)
  const [selectedDraftIds, setSelectedDraftIds] = useState<string[]>([])
  const [draftManagerOpen, setDraftManagerOpen] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const reuseJobId = params.get('reuseJobId')
    const sourceSku = params.get('sourceSku')
    const refSku = params.get('refSku')
    if (reuseJobId) {
      void api.get<JobDetail>(`/v1/tasks/${reuseJobId}`).then((job) => {
        const input = job.input_data
        const first = input?.skus?.[0]
        if (!input || !first) return
        setSku({
          sku_id: first.sku_id,
          product_image_url: first.product_image_url,
          product_name: first.product_name,
          category: first.category,
          target_platforms: first.target_platforms.join(', '),
          output_types: first.output_types,
          style_hint: first.style_hint || '',
          presentation_mode: first.presentation_mode,
          model_preference: first.model_preference,
          market: first.market,
          reference_mode: first.reference_mode,
          ref_sku_id: first.ref_sku_id || '',
          inherits_batch_rules: false,
        })
        setImageModel(input.image_model)
        setAspectRatio(first.aspect_ratio)
        setImageSize(first.image_size)
        setPriority(input.priority)
      }).catch(() => setError('原任务配置读取失败。'))
      return
    }
    const lookups = [sourceSku, refSku].filter(Boolean) as string[]
    if (!lookups.length) return
    void Promise.all(lookups.map((lookup) => api.get<{ products: Array<{ sku_code: string; image_url: string; category: string; description: string }> }>(`/v1/products?q=${encodeURIComponent(lookup)}&page_size=20`).then((result) => result.products.find((item) => item.sku_code === lookup))))
      .then((results) => {
        const source = sourceSku ? results[lookups.indexOf(sourceSku)] : null
        const reference = refSku ? results[lookups.indexOf(refSku)] : null
        if (source) {
          setSku((current) => ({
            ...current,
            sku_id: source.sku_code,
            product_name: source.description || source.sku_code,
            product_image_url: source.image_url,
            category: source.category,
          }))
        }
        if (reference) setSku((current) => ({ ...current, reference_mode: 'specified', ref_sku_id: reference.sku_code }))
      })
      .catch(() => setError('未找到要带入的商品，请从商品库重新选择。'))
  }, [])

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY)
      if (saved) setDrafts(JSON.parse(saved) as GenerationDraft[])
    } catch {
      window.localStorage.removeItem(STORAGE_KEY)
    } finally {
      setHydrated(true)
    }
  }, [])

  useEffect(() => {
    if (hydrated) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts))
  }, [drafts, hydrated])

  const currentDraft = useMemo<GenerationDraft>(() => ({
    id: editingDraftId ?? createId(),
    sku,
    imageModel,
    aspectRatio,
    imageSize,
    priority,
    updatedAt: 0,
  }), [aspectRatio, editingDraftId, imageModel, imageSize, priority, sku])

  const currentIssues = getSkuIssues(sku)
  const selectedDrafts = drafts.filter((draft) => selectedDraftIds.includes(draft.id))

  const currentEstimate = useMemo(() => {
    const platforms = sku.target_platforms.split(',').map((value) => value.trim()).filter(Boolean).length
    const mainImages = sku.output_types.includes('main_image') ? platforms : 0
    const detailImages = sku.output_types.includes('detail_page') ? platforms * 3 : 0
    const pddWhiteImages = sku.output_types.includes('pdd_white_background') ? 1 : 0
    return mainImages + detailImages + pddWhiteImages
  }, [sku])

  const resetEditor = () => {
    setSku(createSku())
    setImageModel('fast')
    setAspectRatio('auto')
    setImageSize('2K')
    setPriority('normal')
    setEditingDraftId(null)
    setError(null)
  }

  const saveDraft = () => {
    const draft = { ...currentDraft, updatedAt: Date.now() }
    setDrafts((current) => editingDraftId
      ? current.map((item) => item.id === editingDraftId ? draft : item)
      : [draft, ...current])
    setSuccess(editingDraftId ? '草稿修改已保存' : '已加入待生成清单')
    resetEditor()
  }

  const editDraft = (draft: GenerationDraft) => {
    setSku(draft.sku)
    setImageModel(draft.imageModel)
    setAspectRatio(draft.aspectRatio)
    setImageSize(draft.imageSize)
    setPriority(draft.priority)
    setEditingDraftId(draft.id)
    setError(null)
    setSuccess(null)
    setDraftManagerOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const removeDraft = (id: string) => {
    setDrafts((current) => current.filter((draft) => draft.id !== id))
    setSelectedDraftIds((current) => current.filter((draftId) => draftId !== id))
    if (editingDraftId === id) resetEditor()
  }

  const duplicateDraft = (draft: GenerationDraft) => {
    const copy = { ...draft, id: createId(), sku: { ...draft.sku, sku_id: `${draft.sku.sku_id}-copy` }, updatedAt: Date.now() }
    setDrafts((current) => [copy, ...current])
  }

  const toggleDraft = (id: string) => {
    setSelectedDraftIds((current) => current.includes(id)
      ? current.filter((draftId) => draftId !== id)
      : [...current, id])
  }

  const submitDrafts = async (items: GenerationDraft[], resetAfterSubmit = false) => {
    setError(null)
    setSuccess(null)

    const invalid = items.find((draft) => getSkuIssues(draft.sku).length > 0)
    if (invalid) {
      setError(`${invalid.sku.sku_id || '未命名 SKU'}：${getSkuIssues(invalid.sku)[0]}`)
      return
    }
    if (items.length === 0) {
      setError('请先选择要提交的商品')
      return
    }

    setSubmitting(true)
    try {
      const jobs = await Promise.all(items.map((draft) => {
        const payload: BatchSubmitPayload = {
          skus: [toSkuInput(draft)],
          image_model: draft.imageModel as BatchSubmitPayload['image_model'],
          video_model: 'veo',
          priority: draft.priority,
        }
        return api.post<{ job_id: string; status: string }>('/v1/batch/submit', payload)
      }))

      const submittedIds = new Set(items.map((draft) => draft.id))
      setDrafts((current) => current.filter((draft) => !submittedIds.has(draft.id)))
      setSelectedDraftIds([])
      setSuccess(items.length === 1 ? `任务已提交：${jobs[0].job_id}` : `已提交 ${jobs.length} 个生成任务`)
      if (resetAfterSubmit || items.some((draft) => draft.id === editingDraftId)) resetEditor()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const submitCurrent = () => submitDrafts([currentDraft], true)

  const draftCard = (draft: GenerationDraft, compact = true) => {
    const issues = getSkuIssues(draft.sku)
    const checked = selectedDraftIds.includes(draft.id)
    return (
      <div key={draft.id} className={`group rounded-lg border p-2.5 transition-colors ${editingDraftId === draft.id ? 'border-primary bg-primary/[0.04]' : 'bg-background hover:bg-muted/25'}`}>
        <div className="flex items-start gap-2.5">
          <input type="checkbox" checked={checked} onChange={() => toggleDraft(draft.id)} className="mt-1 h-4 w-4 shrink-0 rounded border-input accent-primary" aria-label={`选择 ${draft.sku.sku_id || '未命名商品'}`} />
          <button type="button" onClick={() => editDraft(draft)} className="flex min-w-0 flex-1 items-start gap-2.5 text-left">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted/40">
              {draft.sku.product_image_url
                ? <img src={draft.sku.product_image_url} alt={draft.sku.product_name || draft.sku.sku_id} className="h-full w-full object-cover" />
                : <ImageIcon className="h-4 w-4 text-muted-foreground/50" />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{draft.sku.product_name || '未命名商品'}</p>
              <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{draft.sku.sku_id || '未填写 SKU'}</p>
              <div className={`mt-1 flex items-center gap-1 text-[11px] ${issues.length ? 'text-amber-600' : 'text-emerald-600'}`}>
                {issues.length ? <AlertTriangle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3" />}
                <span className="truncate">{issues[0] || '可提交'}</span>
              </div>
            </div>
          </button>
          {!compact && <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-muted-foreground" onClick={() => duplicateDraft(draft)} title="复制配置"><Copy className="h-3.5 w-3.5" /></Button>}
          <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive" onClick={() => removeDraft(draft.id)}>
            <Trash2 className="h-3.5 w-3.5" />
            <span className="sr-only">移除草稿</span>
          </Button>
        </div>
        {!compact && (
          <div className="mt-2 flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
            <span>{draft.sku.target_platforms || '未选平台'} · {draft.aspectRatio} · {draft.imageSize}</span>
            <Button type="button" variant="ghost" size="sm" className="h-7 px-2" onClick={() => editDraft(draft)}><Pencil className="mr-1 h-3 w-3" />编辑</Button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto flex h-full max-w-[1480px] flex-col gap-2 overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b pb-2">
        <div className="mr-auto min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-primary">Product → Reference → Assets</p>
          <h1 className="text-xl font-semibold tracking-tight">图片创作</h1>
          <p className="truncate text-xs text-muted-foreground">一次完成一个商品；多个商品放入待生成清单统一提交。</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => setDraftManagerOpen(true)}><ListChecks className="mr-1.5 h-4 w-4" />待生成 {drafts.length}</Button>
        <Button type="button" variant="outline" size="sm" onClick={resetEditor}><PackagePlus className="mr-1.5 h-4 w-4" />新建商品</Button>
      </header>

      {error && <div className="fixed right-4 top-20 z-50 max-w-md rounded-md border border-destructive/40 bg-background px-4 py-3 text-sm text-destructive shadow-lg">{error}</div>}
      {success && (
        <div className="fixed right-4 top-20 z-50 flex max-w-md flex-wrap items-center gap-3 rounded-md border border-emerald-500/30 bg-background px-4 py-3 text-sm shadow-lg">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          <span>{success}</span>
          {success.includes('提交') && <Button type="button" variant="link" className="h-auto p-0" onClick={() => router.push('/tasks')}>查看任务</Button>}
        </div>
      )}

      <div className="min-h-0 flex-1">
        <main className="min-h-0 min-w-0">
          <section className="flex h-full flex-col overflow-hidden rounded-xl border bg-card">
            <div className="flex shrink-0 flex-wrap items-center gap-3 border-b bg-muted/20 px-3 py-2">
              <div className="mr-auto min-w-0">
                <h2 className="truncate text-sm font-semibold">{editingDraftId ? '编辑待生成商品' : '商品与生成要求'}</h2>
                <p className="text-xs text-muted-foreground">每个商品保留自己的模型、比例、风格与参考图配置</p>
              </div>
              {editingDraftId && <Badge variant="secondary">正在修改草稿</Badge>}
            </div>

            <div className="grid shrink-0 grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2 border-b bg-muted/10 px-3 py-2 text-xs">
              <div className="min-w-0"><p className="font-medium">新品原图</p><p className="truncate text-muted-foreground">{sku.sku_id || '等待上传或选择'}</p></div><ChevronRight className="h-4 w-4 text-muted-foreground" /><div className="min-w-0"><p className="font-medium">爆款参考</p><p className="truncate text-muted-foreground">{sku.reference_mode === 'specified' ? sku.ref_sku_id || '等待选择' : sku.reference_mode === 'none' ? '不使用参考' : '自动匹配'}</p></div><ChevronRight className="h-4 w-4 text-muted-foreground" /><div className="min-w-0"><p className="font-medium">生成结果</p><p className="truncate text-muted-foreground">{currentEstimate} 张 · {sku.target_platforms || '未选平台'}</p></div>
            </div>

            <div className="grid shrink-0 gap-2 border-b bg-muted/[0.06] p-2 sm:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-1"><Label>图片模型</Label><Select value={imageModel} onValueChange={setImageModel}><SelectTrigger className="h-9"><SelectValue /></SelectTrigger><SelectContent>{imageModels.map((model) => <SelectItem key={model.alias} value={model.alias}>{model.label}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-1"><Label>图片比例</Label><Select value={aspectRatio} onValueChange={(value) => setAspectRatio(value as AspectRatio)}><SelectTrigger className="h-9"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="auto">跟随平台规则</SelectItem><SelectItem value="1:1">1:1 方图</SelectItem><SelectItem value="3:4">3:4 竖版</SelectItem><SelectItem value="4:5">4:5 竖版</SelectItem><SelectItem value="9:16">9:16 长竖版</SelectItem><SelectItem value="16:9">16:9 横版</SelectItem><SelectItem value="4:1">4:1 横幅</SelectItem><SelectItem value="1:4">1:4 长竖幅</SelectItem></SelectContent></Select></div>
              <div className="space-y-1"><Label>生成质量</Label><Select value={imageSize} onValueChange={(value) => setImageSize(value as ImageSize)}><SelectTrigger className="h-9"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="1K">1K 预览</SelectItem><SelectItem value="2K">2K 默认</SelectItem><SelectItem value="4K">4K 高清</SelectItem></SelectContent></Select></div>
              <div className="space-y-1"><Label>任务优先级</Label><Select value={priority} onValueChange={(value) => setPriority(value as Priority)}><SelectTrigger className="h-9"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="low">低</SelectItem><SelectItem value="normal">普通</SelectItem><SelectItem value="high">高</SelectItem></SelectContent></Select></div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden p-2">
              <SkuForm sku={sku} index={0} canRemove={false} onChange={setSku} onRemove={() => undefined} embedded showGenerationSettings singleScreen />
            </div>

          <div className="flex shrink-0 flex-col gap-2 border-t bg-background/95 px-3 py-2 sm:flex-row sm:items-center">
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${currentIssues.length ? 'bg-amber-500/10 text-amber-600' : 'bg-emerald-500/10 text-emerald-600'}`}>
                {currentIssues.length ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
              </div>
              <div className="min-w-0 text-sm">
                <p className="font-medium">主图 {sku.output_types.includes('main_image') ? 1 : 0} 张{sku.output_types.includes('detail_page') ? ' · 场景/卖点/特写各 1 张' : ''}</p>
                <p className="truncate text-xs text-muted-foreground">{currentIssues[0] || `${imageModel} · ${aspectRatio === 'auto' ? '跟随平台比例' : aspectRatio} · ${imageSize}`}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={saveDraft}>{editingDraftId ? '保存修改' : '加入待生成清单'}</Button>
              <Button type="button" disabled={submitting} onClick={submitCurrent}>{submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}立即生成</Button>
            </div>
          </div>
          </section>
        </main>
      </div>

      <Dialog open={draftManagerOpen} onOpenChange={setDraftManagerOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>待生成清单 · {drafts.length} 个商品</DialogTitle></DialogHeader>
          <div className="grid max-h-[65vh] gap-2 overflow-y-auto py-1 sm:grid-cols-2">
            {drafts.map((draft) => draftCard(draft, false))}
            {drafts.length === 0 && <div className="col-span-full rounded-lg border border-dashed p-10 text-center"><PackagePlus className="mx-auto h-6 w-6 text-muted-foreground" /><p className="mt-2 text-sm font-medium">还没有待生成商品</p><p className="mt-1 text-xs text-muted-foreground">完成当前商品配置后，点击“加入待生成清单”。</p></div>}
          </div>
          <div className="flex items-center justify-between border-t pt-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={drafts.length > 0 && selectedDraftIds.length === drafts.length} onChange={(event) => setSelectedDraftIds(event.target.checked ? drafts.map((draft) => draft.id) : [])} className="h-4 w-4 rounded border-input accent-primary" />已选 {selectedDraftIds.length} 个，共生成 {selectedDrafts.reduce((sum, draft) => sum + (draft.sku.output_types.includes('detail_page') ? 4 : 1), 0)} 张</label>
            <Button type="button" disabled={submitting || selectedDrafts.length === 0} onClick={() => submitDrafts(selectedDrafts)}>{submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}提交生成</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
