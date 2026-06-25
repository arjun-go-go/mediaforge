'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Trash2 } from 'lucide-react'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { JobStatus } from '@/types/job'

export type JobSummary = {
  job_id: string
  status: string
  total_skus: number
  done_skus: number
  created_at: string | null
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: '等待中',
  running: '运行中',
  done: '已完成',
  partial_fail: '部分失败',
  failed: '失败',
}

const STATUS_VARIANTS: Record<JobStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  running: 'default',
  done: 'outline',
  partial_fail: 'destructive',
  failed: 'destructive',
}

const TERMINAL: ReadonlySet<JobStatus> = new Set(['done', 'failed', 'partial_fail'])

export function JobTable({
  jobs,
  onDelete,
}: {
  jobs: JobSummary[]
  onDelete?: (jobId: string) => Promise<void> | void
}) {
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleDelete = async (e: React.MouseEvent, jobId: string) => {
    e.preventDefault()
    e.stopPropagation()
    if (!onDelete) return
    if (!window.confirm('确定要删除这个任务吗？相关素材也会一并删除。')) return
    setDeletingId(jobId)
    try {
      await onDelete(jobId)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>任务 ID</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>进度</TableHead>
          <TableHead>创建时间</TableHead>
          {onDelete && <TableHead className="w-[60px]"></TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => {
          const status = job.status as JobStatus
          const canDelete = TERMINAL.has(status)
          return (
            <TableRow key={job.job_id} className="cursor-pointer">
              <TableCell>
                <Link
                  href={`/tasks?jobId=${job.job_id}`}
                  className="font-mono text-xs text-primary hover:underline"
                >
                  {job.job_id}
                </Link>
              </TableCell>
              <TableCell>
                <Badge variant={STATUS_VARIANTS[status] ?? 'secondary'}>
                  {STATUS_LABELS[status] ?? job.status}
                </Badge>
              </TableCell>
              <TableCell>
                {job.done_skus}/{job.total_skus} SKUs
              </TableCell>
              <TableCell>{job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</TableCell>
              {onDelete && (
                <TableCell>
                  {canDelete && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                      onClick={(e) => handleDelete(e, job.job_id)}
                      disabled={deletingId === job.job_id}
                      title="删除任务"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              )}
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
