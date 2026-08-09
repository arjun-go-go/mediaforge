'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  ImageIcon,
  LibraryBig,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
} from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'

type OverviewJob = {
  job_id: string
  status: string
  total_skus: number
  done_skus: number
  created_at: string | null
  product_name: string
  sku_id: string
  product_image_url: string
  platforms: string[]
}

type OverviewAsset = {
  asset_id: string
  job_id: string
  sku_id: string
  output_type: string
  platform: string | null
  file_path: string
  created_at: string | null
}

type Overview = {
  active_jobs: OverviewJob[]
  attention_jobs: OverviewJob[]
  recent_jobs: OverviewJob[]
  recent_assets: OverviewAsset[]
  metrics: {
    generated_assets_7d: number
    quality_pass_rate_7d: number | null
    average_duration_seconds_7d: number | null
    active_jobs: number
  }
  analytics: {
    estimated_cost_usd_7d: number
    platforms: Array<{ name: string; count: number }>
    models: Array<{ name: string; total: number; success_rate: number }>
    references: Array<{ sku_id: string; count: number }>
  }
}

const EMPTY: Overview = {
  active_jobs: [], attention_jobs: [], recent_jobs: [], recent_assets: [],
  metrics: { generated_assets_7d: 0, quality_pass_rate_7d: null, average_duration_seconds_7d: null, active_jobs: 0 },
  analytics: { estimated_cost_usd_7d: 0, platforms: [], models: [], references: [] },
}

function durationLabel(seconds: number | null) {
  if (seconds === null) return '暂无数据'
  const minutes = Math.max(1, Math.round(seconds / 60))
  return minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}

function statusLabel(status: string) {
  return ({ pending: '等待中', running: '生成中', done: '已完成', partial_fail: '部分失败', failed: '失败' } as Record<string, string>)[status] || status
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<Overview>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    setError(null)
    try {
      setOverview(await api.get<Overview>('/v1/tasks/overview'))
    } catch (caught) {
      if (!(caught instanceof ApiError && caught.status === 401)) {
        setError(caught instanceof Error ? caught.message : '工作台加载失败')
      }
    } finally {
      if (!quiet) setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(true), 10000)
    return () => window.clearInterval(timer)
  }, [])

  if (loading) return <div className="flex h-full items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>

  return (
    <div className="mx-auto max-w-[1480px] space-y-5">
      <header className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Commerce studio</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">今天从哪里继续？</h1>
          <p className="mt-1 text-sm text-muted-foreground">处理异常、继续生成，或者从最近的结果快速复用。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline"><Link href="/products"><LibraryBig className="mr-2 h-4 w-4" />选择爆款参考</Link></Button>
          <Button asChild><Link href="/batch"><Plus className="mr-2 h-4 w-4" />生成单品爆款图</Link></Button>
        </div>
      </header>

      {error && <div className="flex items-center justify-between rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"><span>{error}</span><Button size="sm" variant="ghost" onClick={() => void load()}><RefreshCw className="h-4 w-4" /></Button></div>}

      {overview.attention_jobs.length > 0 && (
        <section className="flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4 sm:flex-row sm:items-center">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-500"><AlertTriangle className="h-5 w-5" /></div>
          <div className="min-w-0 flex-1">
            <p className="font-medium">有 {overview.attention_jobs.length} 个任务需要处理</p>
            <p className="truncate text-sm text-muted-foreground">{overview.attention_jobs.slice(0, 3).map((job) => job.sku_id || job.product_name).join('、')}</p>
          </div>
          <Button asChild size="sm" variant="outline"><Link href="/tasks">查看失败原因<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['近 7 天生成', `${overview.metrics.generated_assets_7d} 张`, ImageIcon],
          ['一次质检通过率', overview.metrics.quality_pass_rate_7d === null ? '暂无数据' : `${overview.metrics.quality_pass_rate_7d}%`, CheckCircle2],
          ['平均生成耗时', durationLabel(overview.metrics.average_duration_seconds_7d), Clock3],
          ['正在生成', `${overview.metrics.active_jobs} 个任务`, Sparkles],
        ].map(([label, value, Icon]) => (
          <Card key={label as string} className="border-border/80 bg-card/70">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="h-4 w-4" /></div>
              <div><p className="text-xs text-muted-foreground">{label as string}</p><p className="mt-1 text-lg font-semibold tabular-nums">{value as string}</p></div>
            </CardContent>
          </Card>
        ))}
      </section>

      {overview.active_jobs.length > 0 && (
        <section className="rounded-xl border bg-card">
          <div className="flex items-center justify-between border-b px-4 py-3"><div><h2 className="font-semibold">正在生成</h2><p className="text-xs text-muted-foreground">每 10 秒自动更新</p></div><Badge variant="secondary">{overview.active_jobs.length}</Badge></div>
          <div className="divide-y">
            {overview.active_jobs.slice(0, 5).map((job) => {
              const progress = job.total_skus ? Math.round(job.done_skus * 100 / job.total_skus) : 0
              return <Link key={job.job_id} href={`/tasks?jobId=${job.job_id}`} className="grid gap-3 px-4 py-3 transition-colors hover:bg-muted/25 sm:grid-cols-[48px_minmax(0,1fr)_160px_auto] sm:items-center">
                <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-md border bg-muted">{job.product_image_url ? <img src={job.product_image_url} alt={job.product_name} className="h-full w-full object-cover" /> : <ImageIcon className="h-4 w-4 text-muted-foreground" />}</div>
                <div className="min-w-0"><p className="truncate text-sm font-medium">{job.product_name}</p><p className="truncate font-mono text-xs text-muted-foreground">{job.sku_id} · {job.platforms.join(' / ')}</p></div>
                <div><div className="mb-1 flex justify-between text-[11px] text-muted-foreground"><span>{statusLabel(job.status)}</span><span>{progress}%</span></div><Progress value={progress} className="h-1.5" /></div>
                <ArrowRight className="hidden h-4 w-4 text-muted-foreground sm:block" />
              </Link>
            })}
          </div>
        </section>
      )}

      <section>
        <div className="mb-3 flex items-end justify-between"><div><h2 className="font-semibold">最近生成结果</h2><p className="text-xs text-muted-foreground">直接查看、下载，或沿用配置再次生成。</p></div><Button asChild variant="ghost" size="sm"><Link href="/tasks">全部任务<ArrowRight className="ml-1 h-4 w-4" /></Link></Button></div>
        {overview.recent_assets.length ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {overview.recent_assets.map((asset) => <Link key={asset.asset_id} href={`/tasks?jobId=${asset.job_id}`} className="group overflow-hidden rounded-lg border bg-card">
              <div className="aspect-[4/5] overflow-hidden bg-muted"><img src={asset.file_path} alt={asset.sku_id} className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]" /></div>
              <div className="p-2.5"><p className="truncate font-mono text-xs font-medium">{asset.sku_id}</p><p className="mt-1 truncate text-[11px] text-muted-foreground">{asset.platform || '未指定平台'} · {asset.output_type === 'main_image' ? '主图' : '详情图'}</p></div>
            </Link>)}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed p-10 text-center"><ImageIcon className="mx-auto h-6 w-6 text-muted-foreground" /><p className="mt-3 text-sm font-medium">还没有生成结果</p><p className="mt-1 text-xs text-muted-foreground">上传一个商品，生成第一组电商图片。</p><Button asChild className="mt-4" size="sm"><Link href="/batch">开始生成</Link></Button></div>
        )}
      </section>

      <section>
        <div className="mb-3"><h2 className="font-semibold">近 7 天运行观察</h2><p className="text-xs text-muted-foreground">用于判断平台用量、模型稳定性和参考商品复用情况；成本为模型单价估算，不是实际账单。</p></div>
        <div className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between"><p className="text-sm font-medium">平台生成量</p><span className="text-xs text-muted-foreground">成功图片</span></div><div className="mt-4 space-y-3">{overview.analytics.platforms.slice(0, 5).map((item) => <div key={item.name} className="flex items-center justify-between text-sm"><span className="uppercase">{item.name}</span><span className="tabular-nums text-muted-foreground">{item.count} 张</span></div>)}{overview.analytics.platforms.length === 0 && <p className="text-sm text-muted-foreground">暂无数据</p>}</div></div>
          <div className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between"><p className="text-sm font-medium">模型成功率</p><span className="text-xs text-muted-foreground">估算成本 ${overview.analytics.estimated_cost_usd_7d.toFixed(2)}</span></div><div className="mt-4 space-y-3">{overview.analytics.models.slice(0, 4).map((item) => <div key={item.name}><div className="mb-1 flex justify-between gap-3 text-xs"><span className="truncate">{item.name}</span><span className="tabular-nums text-muted-foreground">{item.success_rate}% · {item.total} 次</span></div><Progress value={item.success_rate} className="h-1.5" /></div>)}{overview.analytics.models.length === 0 && <p className="text-sm text-muted-foreground">暂无数据</p>}</div></div>
          <div className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between"><p className="text-sm font-medium">常用爆款参考</p><Button asChild variant="ghost" size="sm" className="h-7"><Link href="/products">去商品库</Link></Button></div><div className="mt-4 space-y-2">{overview.analytics.references.map((item, index) => <Link key={item.sku_id} href={`/batch?refSku=${encodeURIComponent(item.sku_id)}`} className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"><span className="flex h-6 w-6 items-center justify-center rounded bg-muted font-mono text-[10px] text-muted-foreground">{index + 1}</span><span className="min-w-0 flex-1 truncate font-mono">{item.sku_id}</span><span className="text-xs text-muted-foreground">{item.count} 次</span></Link>)}{overview.analytics.references.length === 0 && <p className="text-sm text-muted-foreground">还没有指定参考商品</p>}</div></div>
        </div>
      </section>
    </div>
  )
}
