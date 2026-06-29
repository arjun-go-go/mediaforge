'use client'

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, ImageIcon, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Asset, AssetStatus, BatchSubmitPayload, SkuInput } from '@/types/job'

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

function resolveImgUrl(path: string | null | undefined): string | null {
  if (!path) return null
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (path.startsWith('/')) return path
  return `/outputs/${path}`
}

export function SkuInputList({
  payload,
  assets,
}: {
  payload: BatchSubmitPayload | null
  assets: Asset[]
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
          <SkuRow key={sku.sku_id} sku={sku} assets={assetsBySku.get(sku.sku_id) ?? []} />
        ))}
        {filtered.length === 0 && (
          <p className="py-4 text-center text-xs text-muted-foreground">没有匹配的 SKU。</p>
        )}
      </div>
    </div>
  )
}

function SkuRow({ sku, assets }: { sku: SkuInput; assets: Asset[] }) {
  const [open, setOpen] = useState(false)
  const imgUrl = resolveImgUrl(sku.product_image_url)

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
          {sku.style_hint && <DetailRow label="风格描述">{sku.style_hint}</DetailRow>}
          {imgUrl && (
            <DetailRow label="产品图片">
              <a
                href={imgUrl}
                target="_blank"
                rel="noreferrer"
                className="text-primary hover:underline"
              >
                {sku.product_image_url}
              </a>
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
                        {a.output_type}
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
                    {a.status === 'success' && a.file_path && (
                      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" asChild>
                        <a href={resolveImgUrl(a.file_path) || '#'} target="_blank" rel="noreferrer">
                          查看
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
