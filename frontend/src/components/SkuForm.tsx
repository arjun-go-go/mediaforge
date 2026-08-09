'use client'

import { useState } from 'react'
import { Loader2, Trash2, Upload } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ReferenceProductPicker } from '@/components/ReferenceProductPicker'
import {
  CATEGORY_OPTIONS,
  inferMarketFromPlatforms,
  PLATFORM_OPTIONS,
  platformRuleSummary,
  STYLE_PRESETS,
} from '@/lib/sku-options'
import type { ModelPreference, OutputType, PresentationMode, ReferenceMode } from '@/types/job'

export type Sku = {
  sku_id: string
  product_image_url: string
  product_name: string
  category: string
  target_platforms: string
  output_types: OutputType[]
  style_hint: string
  presentation_mode: PresentationMode
  model_preference: ModelPreference
  market: string
  reference_mode: ReferenceMode
  ref_sku_id: string
  inherits_batch_rules: boolean
}

type SkuFormProps = {
  sku: Sku
  index: number
  canRemove: boolean
  onChange: (sku: Sku) => void
  onRemove: () => void
  embedded?: boolean
  showGenerationSettings?: boolean
  singleScreen?: boolean
}

export function SkuForm({
  sku,
  index,
  canRemove,
  onChange,
  onRemove,
  embedded = false,
  showGenerationSettings = true,
  singleScreen = false,
}: SkuFormProps) {
  const [uploading, setUploading] = useState(false)
  const update = (updates: Partial<Sku>) => onChange({ ...sku, ...updates })

  const selectedPlatforms = sku.target_platforms.split(',').map((value) => value.trim()).filter(Boolean)
  const detailPageSelected = sku.output_types.includes('detail_page')
  const pddSelected = selectedPlatforms.includes('pinduoduo')
  const pddWhiteSelected = sku.output_types.includes('pdd_white_background')

  const toggleDetailPage = () => {
    update({
      output_types: detailPageSelected
        ? sku.output_types.filter((value) => value !== 'detail_page')
        : [...sku.output_types, 'detail_page'],
    })
  }

  const togglePddWhiteBackground = () => {
    update({
      output_types: pddWhiteSelected
        ? sku.output_types.filter((value) => value !== 'pdd_white_background')
        : [...sku.output_types, 'pdd_white_background'],
    })
  }

  const togglePlatform = (platform: string) => {
    const next = selectedPlatforms.includes(platform)
      ? selectedPlatforms.filter((value) => value !== platform)
      : [...selectedPlatforms, platform]
    update({
      target_platforms: next.join(', '),
      market: inferMarketFromPlatforms(next),
      output_types: next.includes('pinduoduo')
        ? sku.output_types
        : sku.output_types.filter((value) => value !== 'pdd_white_background'),
    })
  }

  const toggleStylePreset = (value: string) => {
    const current = sku.style_hint.trim()
    if (current.includes(value)) {
      update({ style_hint: current.split('、').filter((item) => item.trim() !== value).join('、') })
      return
    }
    update({ style_hint: current ? `${current}、${value}` : value })
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
    <div className={embedded ? (singleScreen ? 'space-y-2' : 'space-y-3') : 'rounded-lg border border-border p-4'}>
      {!embedded && (
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">SKU #{index + 1}</h3>
          {canRemove && (
            <Button type="button" variant="ghost" size="icon" onClick={onRemove}>
              <Trash2 className="h-4 w-4 text-destructive" />
              <span className="sr-only">删除此 SKU</span>
            </Button>
          )}
        </div>
      )}

      <div className={singleScreen ? 'space-y-2' : 'space-y-3'}>
        <div className={embedded ? `grid ${singleScreen ? 'gap-2 lg:grid-cols-[112px_minmax(0,1fr)]' : 'gap-3 lg:grid-cols-[140px_minmax(0,1fr)]'}` : 'space-y-4'}>
          <div className="space-y-2">
          <Label>商品主体图</Label>
          <Label
            htmlFor={`upload-${index}`}
            className={`group flex cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-muted/20 transition-colors hover:border-primary/60 hover:bg-primary/[0.03] ${singleScreen ? 'min-h-20' : 'min-h-28'}`}
          >
            {sku.product_image_url ? (
              <div className={`flex w-full items-center gap-4 p-3 ${embedded ? 'flex-col text-center' : ''}`}>
                <img
                  src={sku.product_image_url}
                  alt={`${sku.sku_id || 'SKU'} 商品图`}
                  className={`${singleScreen ? 'h-14 w-14' : embedded ? 'h-20 w-20' : 'h-24 w-24'} rounded-md border bg-background object-cover`}
                />
                <div className="min-w-0 text-sm">
                  <p className="font-medium">点击替换商品图</p>
                  {!embedded && <p className="mt-1 text-xs leading-5 text-muted-foreground">系统会从图片提取颜色、版型和服装结构。</p>}
                </div>
              </div>
            ) : (
              <div className={singleScreen ? 'py-3 text-center' : 'py-6 text-center'}>
                {uploading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : <Upload className="mx-auto h-5 w-5 text-muted-foreground" />}
                <p className="mt-2 text-sm font-medium">上传商品图</p>
                <p className="mt-1 text-xs text-muted-foreground">PNG、JPG 或 WebP</p>
              </div>
            )}
          </Label>
          <input
            id={`upload-${index}`}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => handleUpload(event.target.files?.[0])}
            disabled={uploading}
          />
          <div className="pt-1">
            <ReferenceProductPicker
              compact
              purpose="source"
              value={sku.sku_id}
              onSelect={(product) => update({
                sku_id: product.sku_code,
                product_name: product.description || product.sku_code,
                product_image_url: product.image_url,
                category: product.category,
              })}
            />
          </div>
          </div>
          <div className={`grid content-start ${singleScreen ? 'gap-2 sm:grid-cols-3' : 'gap-3 sm:grid-cols-2'}`}>
            <div className={`space-y-1.5 ${singleScreen ? 'sm:col-span-2' : 'sm:col-span-2'}`}>
              <Label htmlFor={`product-name-${index}`}>商品名称</Label>
              <Input id={`product-name-${index}`} value={sku.product_name} onChange={(event) => update({ product_name: event.target.value })} placeholder="例如：针织开衫半身裙两件套" />
            </div>
            <div className="space-y-1.5">
              <Label>商品类目</Label>
              <Select value={sku.category} onValueChange={(value) => update({ category: value })}>
                <SelectTrigger><SelectValue placeholder="请选择类目" /></SelectTrigger>
                <SelectContent>{CATEGORY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`sku-id-${index}`}>SKU 编码</Label>
              <Input id={`sku-id-${index}`} value={sku.sku_id} onChange={(event) => update({ sku_id: event.target.value })} placeholder="SKU-12345" />
            </div>
            <div className={`space-y-1.5 ${singleScreen ? 'sm:col-span-2' : ''}`}>
              <Label htmlFor={`image-url-${index}`}>图片 URL（可直接粘贴）</Label>
              <Input id={`image-url-${index}`} value={sku.product_image_url} onChange={(event) => update({ product_image_url: event.target.value })} placeholder="https://..." />
            </div>
          </div>
        </div>

        {showGenerationSettings && (
          <div className={`grid border-t xl:grid-cols-12 ${singleScreen ? 'gap-2 pt-2' : 'gap-3 pt-3'}`}>
            <div className="space-y-2 xl:col-span-3">
              <Label>输出类型</Label>
              <div className="flex flex-wrap gap-1.5">
                <Button type="button" size="sm" className="pointer-events-none h-8">主图 1 张</Button>
                <Button type="button" size="sm" className="h-8" variant={detailPageSelected ? 'default' : 'outline'} onClick={toggleDetailPage}>
                  详情图组 3 张
                </Button>
                {pddSelected && (
                  <Button type="button" size="sm" className="h-8" variant={pddWhiteSelected ? 'default' : 'outline'} onClick={togglePddWhiteBackground}>
                    拼多多白底图 1 张
                  </Button>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                单平台基础 {detailPageSelected ? 4 : 1} 张{pddWhiteSelected ? '，另加拼多多白底图 1 张' : ''}
              </p>
            </div>

            <div className="space-y-2 xl:col-span-9">
              <div className="flex items-center justify-between gap-3">
                <Label>目标电商平台</Label>
                <span className="text-[11px] text-muted-foreground">目标市场按平台自动匹配</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {PLATFORM_OPTIONS.map((platform) => (
                  <Button
                    key={platform.value}
                    type="button"
                    size="sm"
                    className="h-8 px-3"
                    variant={selectedPlatforms.includes(platform.value) ? 'default' : 'outline'}
                    onClick={() => togglePlatform(platform.value)}
                    title={platform.hint}
                  >
                    {platform.label}
                  </Button>
                ))}
              </div>
              <p className="truncate text-[11px] text-muted-foreground">{platformRuleSummary(selectedPlatforms)}</p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:col-span-4">
              <div className="space-y-2">
                <Label>展示方式</Label>
                <Select value={sku.presentation_mode} onValueChange={(value) => update({ presentation_mode: value as PresentationMode })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">自动推荐</SelectItem>
                    <SelectItem value="model_wear">模特上身</SelectItem>
                    <SelectItem value="product_only">商品静物</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {sku.presentation_mode !== 'product_only' && (
                <div className="space-y-2">
                  <Label>模特偏好</Label>
                  <Select value={sku.model_preference} onValueChange={(value) => update({ model_preference: value as ModelPreference })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">自动匹配</SelectItem>
                      <SelectItem value="female">女模特</SelectItem>
                      <SelectItem value="male">男模特</SelectItem>
                      <SelectItem value="no_face">不露脸</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="space-y-2 xl:col-span-8">
              <Label>场景与风格</Label>
              <div className="flex flex-wrap gap-1.5">
                {STYLE_PRESETS.map((preset) => {
                  const selected = sku.style_hint.includes(preset.value)
                  return <Button key={preset.value} type="button" variant={selected ? 'default' : 'outline'} size="sm" className="h-8" onClick={() => toggleStylePreset(preset.value)}>{preset.label}</Button>
                })}
              </div>
              <Textarea value={sku.style_hint} onChange={(event) => update({ style_hint: event.target.value })} placeholder="可继续补充具体场景、光线或构图要求" className={`${singleScreen ? 'min-h-10 h-10' : 'min-h-16'} resize-none`} />
            </div>

            <div className={`grid items-start rounded-md border bg-muted/10 md:grid-cols-[minmax(180px,1fr)_260px] xl:col-span-12 ${singleScreen ? 'gap-2 p-2' : 'gap-3 p-3'}`}>
              <div>
                <Label>爆款风格参考</Label>
                <p className="mt-1 text-xs text-muted-foreground">只参考构图、灯光、场景和色彩。</p>
              </div>
              <Select value={sku.reference_mode} onValueChange={(value) => update({ reference_mode: value as ReferenceMode, ref_sku_id: value === 'specified' ? sku.ref_sku_id : '' })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">自动匹配相似爆款</SelectItem>
                  <SelectItem value="specified">指定爆款商品</SelectItem>
                  <SelectItem value="none">不使用参考</SelectItem>
                </SelectContent>
              </Select>
              {sku.reference_mode === 'specified' && <div className="md:col-span-2"><ReferenceProductPicker compact={singleScreen} value={sku.ref_sku_id} onSelect={(product) => update({ ref_sku_id: product.sku_code })} /></div>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
