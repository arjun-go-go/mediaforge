'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, Plus } from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { useModels } from '@/hooks/useModels'
import { SkuForm, type Sku } from '@/components/SkuForm'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { BatchSubmitPayload, SkuInput } from '@/types/job'

const defaultSku = (): Sku => ({
  sku_id: '',
  product_image_url: '',
  product_name: '',
  category: '',
  target_platforms: '',
  output_types: ['main_image'],
  style_hint: '',
  market: 'US',
  ref_sku_id: '',
})

export default function BatchPage() {
  const router = useRouter()
  const { imageModels, videoModels } = useModels()
  const [skus, setSkus] = useState<Sku[]>([defaultSku()])
  const [imageModel, setImageModel] = useState<string>('pro')
  const [videoModel, setVideoModel] = useState<string>('veo')
  const [priority, setPriority] = useState<'low' | 'normal' | 'high'>('normal')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ job_id: string; status: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const updateSku = (index: number, sku: Sku) => {
    setSkus((prev) => prev.map((s, i) => (i === index ? sku : s)))
  }

  const validate = (): string | null => {
    for (const sku of skus) {
      if (!sku.sku_id.trim()) return '请填写 SKU 编码'
      if (!sku.product_name.trim()) return '请填写产品名称'
      if (!sku.category.trim()) return '请填写类目'
      if (!sku.product_image_url.trim()) return '每个 SKU 都需要填写产品图片 URL'
      if (sku.output_types.length === 0) return '至少选择一种输出类型'
    }
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setResult(null)

    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    const payload: BatchSubmitPayload = {
      skus: skus.map(
        (sku): SkuInput => ({
          sku_id: sku.sku_id.trim(),
          product_image_url: sku.product_image_url.trim(),
          product_name: sku.product_name.trim(),
          category: sku.category.trim(),
          target_platforms: sku.target_platforms
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
          output_types: sku.output_types,
          style_hint: sku.style_hint.trim() || null,
          market: sku.market.trim() || 'US',
          ref_sku_id: sku.ref_sku_id.trim() || null,
        })
      ),
      image_model: imageModel as BatchSubmitPayload['image_model'],
      video_model: videoModel as BatchSubmitPayload['video_model'],
      priority,
    }

    setSubmitting(true)
    try {
      const data = await api.post<{ job_id: string; status: string }>('/v1/batch/submit', payload)
      setResult(data)
      setSkus([defaultSku()])
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : '提交失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">批量提交</h2>
        <p className="text-muted-foreground">为一个或多个 SKU 创建新的生成批次。</p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-md border border-primary/50 bg-primary/10 p-4">
          <p className="font-medium">批次已提交</p>
          <p className="text-sm text-muted-foreground">
            任务 ID: <span className="font-mono">{result.job_id}</span> · 状态: {result.status}
          </p>
          <Button
            variant="link"
            className="h-auto p-0"
            onClick={() => router.push(`/tasks?jobId=${result.job_id}`)}
          >
            查看进度
          </Button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>批次设置</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="image-model">图片模型</Label>
              <Select value={imageModel} onValueChange={setImageModel}>
                <SelectTrigger id="image-model">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {imageModels.map((m) => (
                    <SelectItem key={m.alias} value={m.alias}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* Video model selector hidden — video generation not yet available
            <div className="space-y-2">
              <Label htmlFor="video-model">视频模型</Label>
              <Select value={videoModel} onValueChange={setVideoModel}>
                <SelectTrigger id="video-model">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {videoModels.map((m) => (
                    <SelectItem key={m.alias} value={m.alias}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            */}
            <div className="space-y-2">
              <Label htmlFor="priority">优先级</Label>
              <Select value={priority} onValueChange={(v) => setPriority(v as 'low' | 'normal' | 'high')}>
                <SelectTrigger id="priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">低</SelectItem>
                  <SelectItem value="normal">普通</SelectItem>
                  <SelectItem value="high">高</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {skus.map((sku, index) => (
            <SkuForm
              key={index}
              sku={sku}
              index={index}
              canRemove={skus.length > 1}
              onChange={(s) => updateSku(index, s)}
              onRemove={() => setSkus((prev) => prev.filter((_, i) => i !== index))}
            />
          ))}

          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() => setSkus((prev) => [...prev, defaultSku()])}
          >
            <Plus className="mr-2 h-4 w-4" />
            添加 SKU
          </Button>
        </div>

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          提交批次
        </Button>
      </form>
    </div>
  )
}
