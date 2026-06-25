'use client'

import { useEffect, useMemo, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Loader2, RefreshCw, Trash2 } from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { Loading } from '@/components/Loading'
import { JobTable } from '@/components/JobTable'
import { AssetGallery } from '@/components/AssetGallery'
import { SkuInputList } from '@/components/SkuInputList'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Job, JobDetail, JobStatus } from '@/types/job'

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: '等待中',
  running: '运行中',
  done: '已完成',
  partial_fail: '部分失败',
  failed: '失败',
}

const TERMINAL_STATUSES: JobStatus[] = ['done', 'failed', 'partial_fail']

function TaskDetail({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sseConnected, setSseConnected] = useState(false)

  const fetchJob = async (id: string) => {
    setError(null)
    try {
      const data = await api.get<JobDetail>(`/v1/tasks/${id}`)
      setJob(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setError(err instanceof Error ? err.message : '加载任务失败')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    setIsLoading(true)
    fetchJob(jobId)
  }, [jobId])

  useEffect(() => {
    if (TERMINAL_STATUSES.includes(job?.status as JobStatus)) return

    setSseConnected(true)
    const cleanup = api.streamSse(
      `/v1/tasks/${jobId}/stream`,
      (data) => {
        try {
          const parsed = JSON.parse(data)
          setJob((current) => {
            if (!current) return current
            return {
              ...current,
              status: parsed.status ?? current.status,
              done_skus: parsed.done_skus ?? current.done_skus,
              total_skus: parsed.total_skus ?? current.total_skus,
            }
          })
          if (parsed.event === 'done') {
            fetchJob(jobId)
          }
        } catch {
          // Ignore malformed SSE payloads
        }
      },
      () => setSseConnected(false),
      (err) => {
        setSseConnected(false)
        setError(err.message)
      }
    )

    return () => {
      cleanup()
      setSseConnected(false)
    }
  }, [jobId, job?.status])

  if (isLoading) return <Loading />

  if (error || !job) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error || '未找到任务'}
        </div>
        <Button variant="outline" onClick={onBack}>
          返回任务列表
        </Button>
      </div>
    )
  }

  const progress = job.total_skus > 0 ? Math.round((job.done_skus / job.total_skus) * 100) : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">任务详情</h2>
          <p className="font-mono text-sm text-muted-foreground">{job.job_id}</p>
        </div>
        <div className="flex items-center gap-2">
          {sseConnected && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              实时
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => fetchJob(jobId)}>
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
          <Button variant="outline" size="sm" onClick={onBack}>
            返回任务列表
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            状态
            <Badge variant={job.status === 'done' ? 'outline' : 'default'}>
              {STATUS_LABELS[job.status]}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">进度</span>
            <span className="font-medium">
              {job.done_skus}/{job.total_skus} SKUs
            </span>
          </div>
          <Progress value={progress} className="h-2" />
          <div className="grid grid-cols-1 gap-2 pt-2 text-xs text-muted-foreground sm:grid-cols-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide">创建时间</div>
              <div className="text-foreground">{fmtTime(job.created_at)}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide">开始时间</div>
              <div className="text-foreground">{fmtTime(job.started_at)}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide">结束时间</div>
              <div className="text-foreground">{fmtTime(job.finished_at)}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>提交内容</CardTitle>
        </CardHeader>
        <CardContent>
          <SkuInputList payload={job.input_data} assets={job.assets} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>素材</CardTitle>
        </CardHeader>
        <CardContent>
          <AssetGallery assets={job.assets} />
        </CardContent>
      </Card>
    </div>
  )
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function TaskList() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const failedCount = useMemo(() => jobs.filter((j) => j.status === 'failed').length, [jobs])

  const fetchJobs = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await api.get<{ jobs: Job[] }>('/v1/tasks?limit=100')
      setJobs(data.jobs)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setError(err instanceof Error ? err.message : '加载任务列表失败')
    } finally {
      setIsLoading(false)
    }
  }

  const deleteJob = async (jobId: string) => {
    try {
      await api.delete(`/v1/tasks/${jobId}`)
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId))
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setError(err instanceof Error ? err.message : '删除任务失败')
    }
  }

  const deleteAllFailed = async () => {
    if (!window.confirm(`确定要删除全部 ${failedCount} 个失败任务吗？相关素材也会一并删除。`)) return
    setIsBulkDeleting(true)
    setError(null)
    try {
      await api.delete<{ deleted: number }>('/v1/tasks/failed')
      await fetchJobs()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setError(err instanceof Error ? err.message : '批量删除失败')
    } finally {
      setIsBulkDeleting(false)
    }
  }

  useEffect(() => {
    fetchJobs()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">任务列表</h2>
          <p className="text-muted-foreground">当前租户的所有生成任务。</p>
        </div>
        <div className="flex items-center gap-2">
          {failedCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={deleteAllFailed}
              disabled={isBulkDeleting}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className={`mr-2 h-4 w-4 ${isBulkDeleting ? 'animate-pulse' : ''}`} />
              清理失败任务 ({failedCount})
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={fetchJobs} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>最近任务</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Loading />
          ) : jobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无任务。</p>
          ) : (
            <JobTable jobs={jobs} onDelete={deleteJob} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function TasksView() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const jobId = searchParams.get('jobId')

  const clearJob = () => {
    router.push('/tasks')
  }

  return (
    <div className="space-y-8">
      {jobId && <TaskDetail jobId={jobId} onBack={clearJob} />}
      <TaskList />
    </div>
  )
}

export default function TasksPage() {
  return (
    <Suspense fallback={<Loading />}>
      <TasksView />
    </Suspense>
  )
}
