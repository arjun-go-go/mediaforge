'use client'

import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { RefreshCw } from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { Loading } from '@/components/Loading'
import { StatCard } from '@/components/StatCard'
import { JobTable } from '@/components/JobTable'
import { RagIngestCard } from '@/components/RagIngestCard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Job, JobStatus } from '@/types/job'

const STATUS_ORDER: JobStatus[] = ['pending', 'running', 'done', 'partial_fail', 'failed']

const STATUS_COLORS: Record<JobStatus, string> = {
  pending: '#94a3b8',
  running: '#3b82f6',
  done: '#22c55e',
  partial_fail: '#f59e0b',
  failed: '#ef4444',
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: '等待中',
  running: '运行中',
  done: '已完成',
  partial_fail: '部分失败',
  failed: '失败',
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchJobs = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await api.get<{ jobs: Job[] }>('/v1/tasks?limit=100')
      setJobs(data.jobs)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        return
      }
      setError(err instanceof Error ? err.message : '加载任务失败')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
  }, [])

  const stats = useMemo(() => {
    const total = jobs.length
    const active = jobs.filter((j) => j.status === 'pending' || j.status === 'running').length
    const done = jobs.filter((j) => j.status === 'done').length
    const failed = jobs.filter((j) => j.status === 'failed' || j.status === 'partial_fail').length
    const totalSkus = jobs.reduce((sum, j) => sum + j.total_skus, 0)
    return { total, active, done, failed, totalSkus }
  }, [jobs])

  const statusData = useMemo(() => {
    return STATUS_ORDER.map((status) => ({
      name: STATUS_LABELS[status],
      value: jobs.filter((j) => j.status === status).length,
      color: STATUS_COLORS[status],
    })).filter((d) => d.value > 0)
  }, [jobs])

  const recentJobs = useMemo(() => {
    return [...jobs]
      .sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0
        return tb - ta
      })
      .slice(0, 10)
  }, [jobs])

  if (isLoading) return <Loading />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">工作台</h2>
          <p className="text-muted-foreground">生成任务总览。</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchJobs} disabled={isLoading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          刷新
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="任务总数" value={stats.total} />
        <StatCard title="进行中" value={stats.active} />
        <StatCard title="已完成" value={stats.done} />
        <StatCard title="失败/部分失败" value={stats.failed} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>最近任务</CardTitle>
          </CardHeader>
          <CardContent>
            {recentJobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无任务。</p>
            ) : (
              <JobTable jobs={recentJobs} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>状态分布</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {statusData.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无数据。</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" outerRadius={80} label>
                    {statusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>已提交 SKU 总数</CardTitle>
        </CardHeader>
        <CardContent className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={[{ name: 'SKU 总数', value: stats.totalSkus }]}
              margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
            >
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <RagIngestCard />
      </div>
    </div>
  )
}
