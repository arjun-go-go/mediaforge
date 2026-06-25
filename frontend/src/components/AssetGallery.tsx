import { useState } from 'react'
import { AlertCircle, Download, ExternalLink, Image as ImageIcon, Video as VideoIcon } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import type { Asset, AssetStatus } from '@/types/job'

const STATUS_LABEL: Record<AssetStatus, string> = {
  pending: '等待中',
  success: '成功',
  failed: '失败',
  retrying: '重试中',
}

const STATUS_VARIANT: Record<AssetStatus, 'outline' | 'destructive' | 'secondary' | 'default'> = {
  success: 'outline',
  failed: 'destructive',
  retrying: 'secondary',
  pending: 'secondary',
}

function assetUrl(filePath: string): string {
  if (filePath.startsWith('http://') || filePath.startsWith('https://')) return filePath
  if (filePath.startsWith('/')) return filePath
  return `/outputs/${filePath}`
}

export function AssetGallery({ assets }: { assets: Asset[] }) {
  if (assets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
        <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">暂无生成的素材。</p>
      </div>
    )
  }

  const successCount = assets.filter((a) => a.status === 'success').length
  const failedCount = assets.filter((a) => a.status === 'failed').length

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-muted-foreground">共 {assets.length} 个</span>
        {successCount > 0 && (
          <span className="text-green-600 dark:text-green-400">成功 {successCount}</span>
        )}
        {failedCount > 0 && (
          <span className="text-destructive">失败 {failedCount}</span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {assets.map((asset) => (
          <AssetCard key={asset.asset_id} asset={asset} />
        ))}
      </div>
    </div>
  )
}

function AssetCard({ asset }: { asset: Asset }) {
  const isVideo = asset.output_type === 'video'
  const isSuccess = asset.status === 'success' && !!asset.file_path
  const url = isSuccess ? assetUrl(asset.file_path!) : null

  return (
    <Card className="overflow-hidden transition-shadow hover:shadow-md">
      <div className="aspect-square w-full bg-muted">
        {isSuccess && url ? (
          isVideo ? (
            <video src={url} controls className="h-full w-full object-cover" />
          ) : (
            <Dialog>
              <DialogTrigger asChild>
                <button className="block h-full w-full cursor-zoom-in">
                  <img
                    src={url}
                    alt={asset.sku_id}
                    className="h-full w-full object-cover transition-transform hover:scale-105"
                    loading="lazy"
                  />
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-4xl">
                <DialogHeader>
                  <DialogTitle className="font-mono text-sm">
                    {asset.sku_id}
                    {asset.platform ? ` · ${asset.platform}` : ''}
                  </DialogTitle>
                </DialogHeader>
                <div className="flex justify-center">
                  <img
                    src={url}
                    alt={asset.sku_id}
                    className="max-h-[75vh] w-auto rounded-md"
                  />
                </div>
              </DialogContent>
            </Dialog>
          )
        ) : (
          <FailedPlaceholder asset={asset} />
        )}
      </div>
      <CardContent className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate font-mono text-xs font-medium" title={asset.sku_id}>
            {asset.sku_id}
          </span>
          <Badge variant={STATUS_VARIANT[asset.status]} className="shrink-0 text-xs">
            {STATUS_LABEL[asset.status]}
          </Badge>
        </div>
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            {isVideo ? <VideoIcon className="h-3 w-3" /> : <ImageIcon className="h-3 w-3" />}
            {asset.output_type.replace('_', ' ')}
          </span>
          {asset.platform && <span className="truncate">{asset.platform}</span>}
        </div>
        {asset.model_used && (
          <p className="truncate text-xs text-muted-foreground" title={asset.model_used}>
            {asset.model_used}
          </p>
        )}
        {isSuccess && url && (
          <div className="flex gap-1 pt-1">
            <Button
              variant="outline"
              size="sm"
              className="h-7 flex-1 text-xs"
              asChild
            >
              <a href={url} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-1 h-3 w-3" />
                打开
              </a>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 flex-1 text-xs"
              asChild
            >
              <a href={url} download>
                <Download className="mr-1 h-3 w-3" />
                下载
              </a>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function FailedPlaceholder({ asset }: { asset: Asset }) {
  const [showFull, setShowFull] = useState(false)
  const error = asset.error_msg || ''
  const truncated = error.length > 80 ? error.slice(0, 80) + '...' : error

  if (asset.status === 'pending' || asset.status === 'retrying') {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
        {STATUS_LABEL[asset.status]}
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-3 text-center">
      <AlertCircle className="h-6 w-6 text-destructive/70" />
      {error ? (
        <Dialog>
          <DialogTrigger asChild>
            <button
              className="line-clamp-3 cursor-pointer text-xs text-muted-foreground hover:text-foreground"
              title="点击查看完整错误"
            >
              {showFull ? error : truncated}
            </button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>失败原因 — {asset.sku_id}</DialogTitle>
            </DialogHeader>
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
              {error}
            </pre>
          </DialogContent>
        </Dialog>
      ) : (
        <span className="text-xs text-muted-foreground">生成失败</span>
      )}
    </div>
  )
}
