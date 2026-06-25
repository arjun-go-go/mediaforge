'use client'

import { useState } from 'react'
import { Loader2, Trash2, Upload } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { OutputType } from '@/types/job'

const OUTPUT_TYPES: { value: OutputType; label: string }[] = [
  { value: 'main_image', label: '主图' },
  { value: 'detail_page', label: '详情页' },
  // { value: 'video', label: '短视频' },
  { value: 'social', label: '社交素材' },
]

export type Sku = {
  sku_id: string
  product_image_url: string
  product_name: string
  category: string
  target_platforms: string
  output_types: OutputType[]
  style_hint: string
  market: string
  ref_sku_id: string
}

type SkuFormProps = {
  sku: Sku
  index: number
  canRemove: boolean
  onChange: (sku: Sku) => void
  onRemove: () => void
}

export function SkuForm({ sku, index, canRemove, onChange, onRemove }: SkuFormProps) {
  const [uploading, setUploading] = useState(false)

  const update = (updates: Partial<Sku>) => {
    onChange({ ...sku, ...updates })
  }

  const toggleOutputType = (type: OutputType) => {
    const has = sku.output_types.includes(type)
    update({
      output_types: has
        ? sku.output_types.filter((t) => t !== type)
        : [...sku.output_types, type],
    })
  }

  const handleUpload = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    try {
      const { url } = await api.upload(file)
      update({ product_image_url: url })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold">SKU #{index + 1}</h3>
        {canRemove && (
          <Button type="button" variant="ghost" size="icon" onClick={onRemove}>
            <Trash2 className="h-4 w-4 text-destructive" />
            <span className="sr-only">删除此 SKU</span>
          </Button>
        )}
      </div>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor={`sku-id-${index}`}>SKU 编码</Label>
            <Input
              id={`sku-id-${index}`}
              value={sku.sku_id}
              onChange={(e) => update({ sku_id: e.target.value })}
              placeholder="SKU-12345"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`product-name-${index}`}>产品名称</Label>
            <Input
              id={`product-name-${index}`}
              value={sku.product_name}
              onChange={(e) => update({ product_name: e.target.value })}
              placeholder="夏季 T 恤"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`category-${index}`}>类目</Label>
            <Input
              id={`category-${index}`}
              value={sku.category}
              onChange={(e) => update({ category: e.target.value })}
              placeholder="服饰"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`market-${index}`}>目标市场</Label>
            <Input
              id={`market-${index}`}
              value={sku.market}
              onChange={(e) => update({ market: e.target.value })}
              placeholder="US"
              maxLength={3}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`image-url-${index}`}>产品图片 URL</Label>
          <div className="flex gap-2">
            <Input
              id={`image-url-${index}`}
              value={sku.product_image_url}
              onChange={(e) => update({ product_image_url: e.target.value })}
              placeholder="https://..."
              className="flex-1"
            />
            <Label
              htmlFor={`upload-${index}`}
              className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm hover:bg-accent"
            >
              {uploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              上传
            </Label>
            <input
              id={`upload-${index}`}
              type="file"
              accept="image/*,video/*"
              className="hidden"
              onChange={(e) => handleUpload(e.target.files?.[0])}
              disabled={uploading}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>输出类型</Label>
          <div className="flex flex-wrap gap-2">
            {OUTPUT_TYPES.map((type) => (
              <Button
                key={type.value}
                type="button"
                variant={sku.output_types.includes(type.value) ? 'default' : 'outline'}
                size="sm"
                onClick={() => toggleOutputType(type.value)}
              >
                {type.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`platforms-${index}`}>目标平台(逗号分隔)</Label>
          <Input
            id={`platforms-${index}`}
            value={sku.target_platforms}
            onChange={(e) => update({ target_platforms: e.target.value })}
            placeholder="amazon, instagram, tiktok"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`style-${index}`}>风格提示</Label>
          <Textarea
            id={`style-${index}`}
            value={sku.style_hint}
            onChange={(e) => update({ style_hint: e.target.value })}
            placeholder="极简白底、生活化场景、轻奢简约..."
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`ref-sku-${index}`}>
            参考 SKU ID
            <span className="ml-1 text-xs text-muted-foreground">（可选，留空则自动 RAG 检索）</span>
          </Label>
          <Input
            id={`ref-sku-${index}`}
            value={sku.ref_sku_id}
            onChange={(e) => update({ ref_sku_id: e.target.value })}
            placeholder="SKU001"
          />
        </div>
      </div>
    </div>
  )
}
