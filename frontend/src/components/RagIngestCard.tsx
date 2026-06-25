'use client'

import { useEffect, useRef, useState } from 'react'
import { Upload } from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

type RagStatus = { status: string; count: number; backend: string } | null

export function RagIngestCard() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [ragStatus, setRagStatus] = useState<RagStatus>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.ragStatus().then(setRagStatus).catch(() => null)
  }, [])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''

    setUploading(true)
    setResult(null)
    setError(null)

    try {
      const res = await api.ingestCsv(file)
      setResult(`已接收 ${res.accepted} 个产品。正在后台索引。`)
      const updated = await api.ragStatus().catch(() => null)
      if (updated) setRagStatus(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>产品参考库</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">向量存储</span>
          <span className="font-medium capitalize">{ragStatus?.backend ?? '—'}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">已索引产品</span>
          <span className="font-medium">{ragStatus?.count ?? '—'}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">状态</span>
          <span
            className={
              ragStatus?.status === 'ok'
                ? 'text-green-600 font-medium'
                : 'text-amber-500 font-medium'
            }
          >
            {ragStatus?.status ?? '未知'}
          </span>
        </div>

        <div className="pt-2 border-t">
          <p className="text-xs text-muted-foreground mb-3">
            上传 CSV 或 Excel 文件以将产品添加到 RAG 参考库。
            必需列：<code className="bg-muted px-1 rounded">product_id, category, style, color, material</code>
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? '上传中…' : '导入 CSV / Excel'}
          </Button>
        </div>

        {result && (
          <p className="text-xs text-green-600 bg-green-50 rounded p-2">{result}</p>
        )}
        {error && (
          <p className="text-xs text-destructive bg-destructive/10 rounded p-2">{error}</p>
        )}
      </CardContent>
    </Card>
  )
}
