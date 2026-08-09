'use client'

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, ImageIcon, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type {
  Asset,
  AssetStatus,
  BatchSubmitPayload,
  GenerationContext,
  JobItem,
  ReferenceProductSummary,
  SkuInput,
} from '@/types/job'

const ASSET_STATUS_LABEL: Record<AssetStatus, string> = {
  pending: '等待',
  success: '成功',
  failed: '失败',
  retrying: '重试',
}

const ASSET_STATUS_COLOR: Record<AssetStatus, string> = {
  success: 'text-green-600 dark:text-green-400',
  failed: 'text-destructive',
  retrying: 'text-amber-500',
  pending: 'text-muted-foreground',
}

const PRESENTATION_LABEL = {
  auto: '自动推荐',
  model_wear: '模特上身',
  product_only: '商品静物',
} as const

const MODEL_PREFERENCE_LABEL = {
  auto: '自动匹配',
  female: '女模特',
  male: '男模特',
  no_face: '不露脸',
} as const

function resolveImgUrl(path: string | null | undefined): string | null {
  if (!path) return null
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (path.startsWith('/')) return path
  return path
}

export function SkuInputList({
  payload,
  assets,
  referenceProducts,
  jobItems,
}: {
  payload: BatchSubmitPayload | null
  assets: Asset[]
  referenceProducts: Record<string, ReferenceProductSummary>
  jobItems: JobItem[]
}) {
  const [query, setQuery] = useState('')

  const assetsBySku = useMemo(() => {
    const map = new Map<string, Asset[]>()
    for (const a of assets) {
      const list = map.get(a.sku_id) ?? []
      list.push(a)
      map.set(a.sku_id, list)
    }
    return map
  }, [assets])

  const contextBySku = useMemo(() => {
    const map = new Map<string, GenerationContext>()
    for (const item of jobItems) {
      const context = item.generation_context
      if (!context || Object.keys(context).length === 0) continue
      map.set(item.sku_id, {
        ...context,
        retrieval_routes: context.retrieval_routes ?? [],
        reference_candidates: context.reference_candidates ?? [],
        prompts: context.prompts ?? {},
        quality_results: context.quality_results ?? [],
        presentation_mode: context.presentation_mode ?? 'product_only',
        model_preference: context.model_preference ?? 'auto',
        product_attributes: context.product_attributes ?? {},
        retry_count: context.retry_count ?? 0,
        retry_mode: context.retry_mode ?? 'none',
      })
    }
    return map
  }, [jobItems])

  if (!payload || !payload.skus?.length) {
    return <p className="text-sm text-muted-foreground">未找到提交内容。</p>
  }

  const lowerQ = query.trim().toLowerCase()
  const filtered = lowerQ
    ? payload.skus.filter(
        (s) =>
          s.sku_id.toLowerCase().includes(lowerQ) ||
          s.product_name.toLowerCase().includes(lowerQ) ||
          s.category.toLowerCase().includes(lowerQ),
      )
    : payload.skus

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline" className="font-normal">
          图片模型 {payload.image_model}
        </Badge>
        <Badge variant="outline" className="font-normal">
          优先级 {payload.priority}
        </Badge>
        <span className="ml-auto">共 {payload.skus.length} 个 SKU</span>
      </div>

      {payload.skus.length > 5 && (
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="按 SKU ID / 名称 / 分类筛选"
            className="h-8 pl-8 text-xs"
          />
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((sku) => (
          <SkuRow
            key={sku.sku_id}
            sku={sku}
            assets={assetsBySku.get(sku.sku_id) ?? []}
            referenceProduct={sku.ref_sku_id ? referenceProducts[sku.ref_sku_id] : undefined}
            generationContext={contextBySku.get(sku.sku_id)}
          />
        ))}
        {filtered.length === 0 && (
          <p className="py-4 text-center text-xs text-muted-foreground">没有匹配的 SKU。</p>
        )}
      </div>
    </div>
  )
}

function SkuRow({
  sku,
  assets,
  referenceProduct,
  generationContext,
}: {
  sku: SkuInput
  assets: Asset[]
  referenceProduct?: ReferenceProductSummary
  generationContext?: GenerationContext
}) {
  const [open, setOpen] = useState(false)
  const imgUrl = resolveImgUrl(sku.product_image_url)
  const selectedCandidate = generationContext?.reference_candidates.find(
    (candidate) => candidate.product_id === generationContext.selected_reference_id,
  ) ?? generationContext?.reference_candidates[0]
  const effectiveReference = referenceProduct
    ? {
        code: referenceProduct.sku_code,
        imageUrl: referenceProduct.image_url,
        description: referenceProduct.description || referenceProduct.category,
      }
    : selectedCandidate
      ? {
          code: selectedCandidate.product_id,
          imageUrl: selectedCandidate.image_url,
          description: String(selectedCandidate.metadata?.text || selectedCandidate.metadata?.category || ''),
        }
      : undefined

  const successN = assets.filter((a) => a.status === 'success').length
  const failedN = assets.filter((a) => a.status === 'failed').length
  const pendingN = assets.filter((a) => a.status !== 'success' && a.status !== 'failed').length

  return (
    <div className="rounded-md border bg-card transition-colors hover:bg-accent/30">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-3 text-left"
      >
        <div className="h-12 w-12 shrink-0 overflow-hidden rounded bg-muted">
          {imgUrl ? (
            <img src={imgUrl} alt={sku.sku_id} className="h-full w-full object-cover" loading="lazy" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <ImageIcon className="h-4 w-4 text-muted-foreground/50" />
            </div>
          )}
        </div>

        {effectiveReference?.imageUrl && (
          <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded border border-primary/30 bg-muted">
            <img
              src={effectiveReference.imageUrl}
              alt={`爆款参考 ${effectiveReference.code}`}
              className="h-full w-full object-cover"
              loading="lazy"
            />
            <span className="absolute inset-x-0 bottom-0 bg-black/65 py-0.5 text-center text-[9px] text-white">
              参考图
            </span>
          </div>
        )}

        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-xs font-medium">{sku.sku_id}</span>
            <span className="truncate text-xs text-muted-foreground">{sku.product_name}</span>
          </div>
          <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
            <Badge variant="secondary" className="h-4 px-1.5 text-[10px] font-normal">
              {sku.category}
            </Badge>
            <span>·</span>
            <span>{sku.target_platforms.join(', ') || '—'}</span>
            <span>·</span>
            <span>{sku.market}</span>
            {sku.ref_sku_id && (
              <>
                <span>·</span>
                <span>参考 {sku.ref_sku_id}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 text-xs">
          {successN > 0 && (
            <span className="text-green-600 dark:text-green-400">✓ {successN}</span>
          )}
          {failedN > 0 && <span className="text-destructive">✗ {failedN}</span>}
          {pendingN > 0 && <span className="text-muted-foreground">⋯ {pendingN}</span>}
          {open ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {open && (
        <div className="space-y-3 border-t bg-muted/30 px-3 py-3 text-xs">
          <DetailRow label="输出类型">{sku.output_types.join(', ')}</DetailRow>
          <DetailRow label="展示方式">
            {PRESENTATION_LABEL[sku.presentation_mode ?? 'auto']}
            {generationContext?.presentation_mode && (
              <span className="ml-2 text-muted-foreground">
                · 实际使用 {PRESENTATION_LABEL[generationContext.presentation_mode]}
              </span>
            )}
          </DetailRow>
          {(generationContext?.presentation_mode === 'model_wear' || sku.presentation_mode === 'model_wear') && (
            <DetailRow label="模特偏好">
              {MODEL_PREFERENCE_LABEL[sku.model_preference ?? 'auto']}
            </DetailRow>
          )}
          {sku.style_hint && <DetailRow label="场景与风格">{sku.style_hint}</DetailRow>}
          {effectiveReference?.imageUrl && (
            <DetailRow label="爆款参考">
              <div className="flex items-center gap-3">
                <Dialog>
                  <DialogTrigger asChild>
                    <button
                      type="button"
                      className="group relative h-20 w-20 shrink-0 cursor-zoom-in overflow-hidden rounded-md border bg-muted"
                      title="点击放大"
                    >
                      <img
                        src={effectiveReference.imageUrl}
                        alt={effectiveReference.code}
                        className="h-full w-full object-cover transition-transform group-hover:scale-105"
                        loading="lazy"
                      />
                      <span className="absolute inset-x-0 bottom-0 bg-black/65 py-0.5 text-center text-[10px] text-white">
                        点击放大
                      </span>
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-4xl">
                    <DialogHeader>
                      <DialogTitle className="text-sm">
                        爆款参考图 · {effectiveReference.code}
                      </DialogTitle>
                    </DialogHeader>
                    <div className="flex justify-center">
                      <img
                        src={effectiveReference.imageUrl}
                        alt={effectiveReference.code}
                        className="max-h-[75vh] w-auto rounded-md object-contain"
                      />
                    </div>
                  </DialogContent>
                </Dialog>
                <div className="min-w-0">
                  <div className="font-mono font-medium">{effectiveReference.code}</div>
                  <div className="mt-1 line-clamp-2 text-muted-foreground">
                    {effectiveReference.description}
                  </div>
                  <a
                    href={effectiveReference.imageUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block text-primary hover:underline"
                  >
                    打开原图
                  </a>
                </div>
              </div>
            </DetailRow>
          )}
          {generationContext && (
            <div className="space-y-2 rounded-md border bg-background p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground">检索链路</span>
                {generationContext.retrieval_routes.map((route) => (
                  <Badge key={route} variant="outline" className="h-5 text-[10px] font-normal">
                    {route}
                  </Badge>
                ))}
                {generationContext.retry_count > 0 && (
                  <Badge variant="secondary" className="h-5 text-[10px] font-normal">
                    已重试 · {generationContext.retry_mode}
                  </Badge>
                )}
              </div>
              {generationContext.reference_candidates.length > 1 && (
                <div>
                  <div className="mb-1.5 text-muted-foreground">
                    Top-{generationContext.reference_candidates.length} 爆款候选
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {generationContext.reference_candidates.map((candidate, index) => (
                      <Dialog key={candidate.product_id}>
                        <DialogTrigger asChild>
                          <button
                            type="button"
                            className="relative h-16 w-16 cursor-zoom-in overflow-hidden rounded border bg-muted"
                            title={`${candidate.product_id} · ${candidate.score.toFixed(3)}`}
                          >
                            <img
                              src={candidate.image_url}
                              alt={candidate.product_id}
                              className="h-full w-full object-cover"
                              loading="lazy"
                            />
                            <span className="absolute left-1 top-1 rounded bg-black/65 px-1 text-[9px] text-white">
                              #{index + 1}
                            </span>
                          </button>
                        </DialogTrigger>
                        <DialogContent className="max-w-4xl">
                          <DialogHeader>
                            <DialogTitle className="text-sm">
                              候选 #{index + 1} · {candidate.product_id}
                            </DialogTitle>
                          </DialogHeader>
                          <div className="flex justify-center">
                            <img
                              src={candidate.image_url}
                              alt={candidate.product_id}
                              className="max-h-[75vh] w-auto rounded-md object-contain"
                            />
                          </div>
                        </DialogContent>
                      </Dialog>
                    ))}
                  </div>
                </div>
              )}
              {generationContext.style_prompt && (
                <div>
                  <div className="text-muted-foreground">共同风格提示</div>
                  <p className="mt-1 whitespace-pre-wrap leading-5">{generationContext.style_prompt}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {Object.keys(generationContext.product_attributes).length > 0 && (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button type="button" variant="outline" size="sm" className="h-7 text-xs">
                        查看服装结构
                      </Button>
                    </DialogTrigger>
                    <DialogContent className="max-w-2xl">
                      <DialogHeader><DialogTitle>服装结构 · {sku.sku_id}</DialogTitle></DialogHeader>
                      <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                        {JSON.stringify(generationContext.product_attributes, null, 2)}
                      </pre>
                    </DialogContent>
                  </Dialog>
                )}
                {Object.keys(generationContext.prompts).length > 0 && (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button type="button" variant="outline" size="sm" className="h-7 text-xs">
                        查看最终提示词 ({Object.keys(generationContext.prompts).length})
                      </Button>
                    </DialogTrigger>
                    <DialogContent className="max-w-3xl">
                      <DialogHeader><DialogTitle>最终提示词 · {sku.sku_id}</DialogTitle></DialogHeader>
                      <div className="max-h-[65vh] space-y-3 overflow-auto">
                        {Object.entries(generationContext.prompts).map(([asset, prompt]) => (
                          <div key={asset}>
                            <div className="mb-1 font-mono text-xs font-medium">{asset}</div>
                            <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">{prompt}</pre>
                          </div>
                        ))}
                      </div>
                    </DialogContent>
                  </Dialog>
                )}
                {generationContext.quality_results.length > 0 && (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button type="button" variant="outline" size="sm" className="h-7 text-xs">
                        查看质检记录 ({generationContext.quality_results.length})
                      </Button>
                    </DialogTrigger>
                    <DialogContent className="max-w-3xl">
                      <DialogHeader><DialogTitle>质检记录 · {sku.sku_id}</DialogTitle></DialogHeader>
                      <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                        {JSON.stringify(generationContext.quality_results, null, 2)}
                      </pre>
                    </DialogContent>
                  </Dialog>
                )}
              </div>
            </div>
          )}
          {imgUrl && (
            <DetailRow label="用户上传图">
              <div className="flex items-center gap-3">
                <Dialog>
                  <DialogTrigger asChild>
                    <button
                      type="button"
                      className="group relative h-20 w-20 shrink-0 cursor-zoom-in overflow-hidden rounded-md border bg-muted"
                      title="点击放大"
                    >
                      <img
                        src={imgUrl}
                        alt={sku.product_name || sku.sku_id}
                        className="h-full w-full object-cover transition-transform group-hover:scale-105"
                        loading="lazy"
                      />
                      <span className="absolute inset-x-0 bottom-0 bg-black/65 py-0.5 text-center text-[10px] text-white">
                        点击放大
                      </span>
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-4xl">
                    <DialogHeader>
                      <DialogTitle className="text-sm">
                        用户上传图 · {sku.product_name || sku.sku_id}
                      </DialogTitle>
                    </DialogHeader>
                    <div className="flex justify-center">
                      <img
                        src={imgUrl}
                        alt={sku.product_name || sku.sku_id}
                        className="max-h-[75vh] w-auto rounded-md object-contain"
                      />
                    </div>
                  </DialogContent>
                </Dialog>
                <div className="min-w-0">
                  <div className="font-medium">{sku.product_name || sku.sku_id}</div>
                  <a
                    href={imgUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block text-primary hover:underline"
                  >
                    打开原图
                  </a>
                </div>
              </div>
            </DetailRow>
          )}

          {assets.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-muted-foreground">生成结果 ({assets.length})</div>
              <div className="space-y-1">
                {assets.map((a) => (
                  <div
                    key={a.asset_id}
                    className="flex items-center justify-between gap-2 rounded border bg-background px-2 py-1.5"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span className={`shrink-0 font-medium ${ASSET_STATUS_COLOR[a.status]}`}>
                        {ASSET_STATUS_LABEL[a.status]}
                      </span>
                      <span className="truncate text-muted-foreground">
                        {a.output_type === 'pdd_white_background' ? '拼多多白底图' : a.output_type}
                        {a.platform ? ` · ${a.platform}` : ''}
                      </span>
                    </div>
                    {a.status === 'failed' && a.error_msg && (
                      <span
                        className="line-clamp-1 max-w-[60%] text-destructive/70"
                        title={a.error_msg}
                      >
                        {a.error_msg}
                      </span>
                    )}
                    {a.file_path && (
                      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" asChild>
                        <a href={resolveImgUrl(a.file_path) || '#'} target="_blank" rel="noreferrer">
                          {a.status === 'failed' ? '查看失败图' : '查看'}
                        </a>
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="w-16 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-all">{children}</span>
    </div>
  )
}
