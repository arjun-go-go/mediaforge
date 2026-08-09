'use client'

import { useEffect, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, ImageIcon, Loader2, Search } from 'lucide-react'

import { api } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export type ReferenceProduct = {
  sku_code: string
  category: string
  description: string
  image_url: string
  sales_count: number
  visibility?: 'global' | 'private'
}

type ProductPage = {
  products: ReferenceProduct[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 12

export function ReferenceProductPicker({
  value,
  onSelect,
  compact = false,
  purpose = 'reference',
}: {
  value: string
  onSelect: (product: ReferenceProduct) => void
  compact?: boolean
  purpose?: 'reference' | 'source'
}) {
  const [open, setOpen] = useState(false)
  const [queryInput, setQueryInput] = useState('')
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<'all' | 'global' | 'private'>('all')
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState<'sales_desc' | 'updated_desc'>('sales_desc')
  const [page, setPage] = useState(1)
  const [products, setProducts] = useState<ReferenceProduct[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<ReferenceProduct | null>(null)
  const [pendingProduct, setPendingProduct] = useState<ReferenceProduct | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim())
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [queryInput])

  useEffect(() => {
    if (!value) setSelectedProduct(null)
  }, [value])

  useEffect(() => {
    if (!open) return
    api.get<{ categories: string[] }>(`/v1/products/categories?scope=${scope}`)
      .then((data) => setCategories(data.categories))
      .catch(() => setCategories([]))
  }, [open, scope])

  useEffect(() => {
    if (!open) return
    const params = new URLSearchParams({
      scope,
      sort,
      page: String(page),
      page_size: String(PAGE_SIZE),
    })
    if (query) params.set('q', query)
    if (category !== 'all') params.set('category', category)

    setLoading(true)
    setError(null)
    api.get<ProductPage>(`/v1/products?${params.toString()}`)
      .then((data) => {
        setProducts(data.products)
        setTotal(data.total)
        const current = data.products.find((product) => product.sku_code === value)
        if (current && !selectedProduct) setSelectedProduct(current)
      })
      .catch((err) => {
        setProducts([])
        setTotal(0)
        setError(err instanceof Error ? err.message : '加载爆款商品失败')
      })
      .finally(() => setLoading(false))
  }, [open, query, scope, category, sort, page, value, selectedProduct])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const openPicker = () => {
    setPendingProduct(selectedProduct)
    setPage(1)
    setOpen(true)
  }

  const confirm = () => {
    if (!pendingProduct) return
    setSelectedProduct(pendingProduct)
    onSelect(pendingProduct)
    setOpen(false)
  }

  return (
    <>
      {selectedProduct ? (
        <div className={`flex items-center rounded-md border border-primary/40 bg-primary/5 ${compact ? 'gap-2 p-2' : 'gap-3 p-3'}`}>
          <img
            src={selectedProduct.image_url}
            alt={selectedProduct.sku_code}
            className={`${compact ? 'h-11 w-11' : 'h-16 w-16'} rounded-md border object-cover`}
          />
          <div className="min-w-0 flex-1">
            <p className="font-mono text-sm font-medium">{selectedProduct.sku_code}</p>
            <p className="truncate text-xs text-muted-foreground">
              {selectedProduct.description || selectedProduct.category}
            </p>
            <p className={`mt-1 text-xs text-muted-foreground ${compact ? 'hidden' : ''}`}>
              销量 {selectedProduct.sales_count.toLocaleString()}
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={openPicker}>更换</Button>
        </div>
      ) : (
        <Button type="button" variant="outline" className="w-full" onClick={openPicker}>
          <Search className="mr-2 h-4 w-4" />
          {value
            ? `重新选择商品（当前 ${value}）`
            : purpose === 'source' ? '从商品库选择' : '选择爆款商品'}
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[88vh] max-w-5xl flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle>{purpose === 'source' ? '选择要处理的商品' : '选择爆款参考'}</DialogTitle>
            <DialogDescription>
              {purpose === 'source'
                ? '助手会把商品编码、类目、描述和图片作为本次对话的商品上下文。'
                : '参考图用于学习构图、灯光和场景，不会替换当前商品主体。'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_150px_150px_150px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="搜索 SKU、描述、类目、风格或颜色"
                className="pl-9"
              />
            </div>
            <Select value={scope} onValueChange={(next) => { setScope(next as typeof scope); setCategory('all'); setPage(1) }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部商品</SelectItem>
                <SelectItem value="global">公共爆款</SelectItem>
                <SelectItem value="private">我的商品</SelectItem>
              </SelectContent>
            </Select>
            <Select value={category} onValueChange={(next) => { setCategory(next); setPage(1) }}>
              <SelectTrigger><SelectValue placeholder="全部类目" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类目</SelectItem>
                {categories.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={(next) => { setSort(next as typeof sort); setPage(1) }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="sales_desc">销量优先</SelectItem>
                <SelectItem value="updated_desc">最近更新</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="min-h-[320px] flex-1 overflow-y-auto rounded-md border bg-muted/10 p-3">
            {loading ? (
              <div className="flex h-72 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />加载商品中
              </div>
            ) : error ? (
              <div className="flex h-72 items-center justify-center text-sm text-destructive">{error}</div>
            ) : products.length === 0 ? (
              <div className="flex h-72 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <ImageIcon className="h-8 w-8" />
                没有找到匹配的爆款商品
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {products.map((product) => {
                  const selected = pendingProduct?.sku_code === product.sku_code
                  return (
                    <button
                      key={product.sku_code}
                      type="button"
                      onClick={() => setPendingProduct(product)}
                      className={`group overflow-hidden rounded-md border bg-card text-left transition-all hover:border-primary/60 ${selected ? 'border-primary ring-2 ring-primary/20' : ''}`}
                    >
                      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
                        {product.image_url ? (
                          <img src={product.image_url} alt="" className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]" />
                        ) : (
                          <div className="flex h-full items-center justify-center"><ImageIcon className="h-6 w-6 text-muted-foreground" /></div>
                        )}
                        {selected && (
                          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
                            <Check className="h-4 w-4" />
                          </span>
                        )}
                      </div>
                      <div className="space-y-1 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate font-mono text-xs font-semibold">{product.sku_code}</span>
                          <Badge variant="secondary" className="shrink-0 text-[10px]">{product.category}</Badge>
                        </div>
                        <p className="line-clamp-2 h-8 text-xs text-muted-foreground">{product.description || '暂无商品描述'}</p>
                        <p className="text-xs font-medium text-primary">销量 {product.sales_count.toLocaleString()}</p>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">共 {total} 个商品</span>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((current) => current - 1)}>
                <ChevronLeft className="mr-1 h-4 w-4" />上一页
              </Button>
              <span className="min-w-20 text-center text-xs">{page} / {pageCount}</span>
              <Button type="button" variant="outline" size="sm" disabled={page >= pageCount || loading} onClick={() => setPage((current) => current + 1)}>
                下一页<ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>取消</Button>
            <Button type="button" disabled={!pendingProduct} onClick={confirm}>使用这个爆款</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
