'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  ImageIcon,
  LayoutGrid,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type Product = {
  document_id: string
  sku_code: string
  visibility: 'global' | 'private'
  source_type: string
  category: string
  style: string
  color: string
  material: string
  season: string
  description: string
  sales_count: number
  price: string | null
  image_url: string
  index_status: string
  index_error: string | null
  indexed_at: string | null
  updated_at: string
}

type Summary = { global_count: number; private_count: number; indexing_count: number; failed_count: number }
type Filters = { categories: string[]; styles: string[]; colors: string[] }
type PreviewRow = { productId: string; imageRef: string; matched: boolean }

const PAGE_SIZE = 24
const EMPTY_SUMMARY: Summary = { global_count: 0, private_count: 0, indexing_count: 0, failed_count: 0 }
const EMPTY_FILTERS: Filters = { categories: [], styles: [], colors: [] }

function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let value = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') { value += '"'; index += 1 } else quoted = !quoted
    } else if (char === ',' && !quoted) { row.push(value); value = '' }
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[index + 1] === '\n') index += 1
      row.push(value); if (row.some((cell) => cell.trim())) rows.push(row); row = []; value = ''
    } else value += char
  }
  row.push(value); if (row.some((cell) => cell.trim())) rows.push(row)
  return rows
}

function basename(value: string) {
  const withoutQuery = value.split(/[?#]/, 1)[0]
  return withoutQuery.split(/[\\/]/).pop()?.toLowerCase() || ''
}

function indexLabel(status: string) {
  if (status === 'indexed') return '可检索'
  if (status === 'failed') return '索引失败'
  if (status === 'indexing') return '索引中'
  return '等待索引'
}

export default function ProductsPage() {
  const router = useRouter()
  const catalogInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [scope, setScope] = useState<'all' | 'global' | 'private'>('all')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [style, setStyle] = useState('all')
  const [color, setColor] = useState('all')
  const [indexStatus, setIndexStatus] = useState('all')
  const [sort, setSort] = useState('sales_desc')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [catalog, setCatalog] = useState<File | null>(null)
  const [images, setImages] = useState<File[]>([])
  const [preview, setPreview] = useState<PreviewRow[]>([])
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setPage(1) }, 300)
    return () => window.clearTimeout(timer)
  }, [search])

  const loadProducts = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    setLoadError(null)
    try {
      const params = new URLSearchParams({ scope, page: String(page), page_size: String(PAGE_SIZE), sort })
      if (query) params.set('q', query)
      if (category !== 'all') params.set('category', category)
      if (style !== 'all') params.set('style', style)
      if (color !== 'all') params.set('color', color)
      if (indexStatus !== 'all') params.set('index_status', indexStatus)
      const [list, totals, available] = await Promise.all([
        api.get<{ products: Product[]; total: number }>(`/v1/products?${params.toString()}`),
        api.get<Summary>('/v1/products/summary'),
        api.get<Filters>(`/v1/products/filters?scope=${scope}`),
      ])
      setProducts(list.products); setTotal(list.total); setSummary(totals); setFilters(available)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '商品数据加载失败')
    } finally { if (!quiet) setLoading(false) }
  }, [scope, page, query, category, style, color, indexStatus, sort])

  useEffect(() => { void loadProducts() }, [loadProducts])
  useEffect(() => {
    if (summary.indexing_count === 0) return
    const timer = window.setInterval(() => void loadProducts(true), 3000)
    return () => window.clearInterval(timer)
  }, [loadProducts, summary.indexing_count])

  useEffect(() => {
    let cancelled = false
    async function buildPreview() {
      if (!catalog || !catalog.name.toLowerCase().endsWith('.csv')) { setPreview([]); return }
      setPreviewing(true)
      try {
        const rows = parseCsv(await catalog.text())
        const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, '').trim())
        const productIndex = headers.indexOf('product_id')
        const imageIndex = headers.findIndex((header) => header === 'image_path' || header === 'image_url')
        const selectedNames = new Set(images.map((image) => image.name.toLowerCase()))
        const next = rows.map((cells) => {
          const imageRef = imageIndex >= 0 ? (cells[imageIndex] || '').trim() : ''
          return { productId: productIndex >= 0 ? (cells[productIndex] || '').trim() : '', imageRef, matched: /^https?:\/\//i.test(imageRef) || selectedNames.has(basename(imageRef)) }
        }).filter((row) => row.productId)
        if (!cancelled) setPreview(next)
      } finally { if (!cancelled) setPreviewing(false) }
    }
    void buildPreview(); return () => { cancelled = true }
  }, [catalog, images])

  const matchedCount = preview.filter((row) => row.matched).length
  const allImagesMatched = Boolean(catalog) && (!catalog?.name.toLowerCase().endsWith('.csv') || (preview.length > 0 && matchedCount === preview.length))
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  async function handleImport() {
    if (!catalog) return
    setImporting(true); setImportError(null); setImportResult(null)
    try {
      const result = await api.ingestProducts(catalog, images)
      setImportResult(`已接收 ${result.accepted} 个商品，正在后台建立索引。`)
      setCatalog(null); setImages([]); setPreview([])
      if (catalogInputRef.current) catalogInputRef.current.value = ''
      if (imageInputRef.current) imageInputRef.current.value = ''
      window.setTimeout(() => { void loadProducts(true); setImportOpen(false); setImportResult(null) }, 1200)
    } catch (error) {
      setImportError(error instanceof ApiError ? error.message : '导入失败，请检查表格和图片匹配关系。')
    } finally { setImporting(false) }
  }

  const createWith = (product: Product, purpose: 'source' | 'reference') => {
    const key = purpose === 'source' ? 'sourceSku' : 'refSku'
    router.push(`/batch?${key}=${encodeURIComponent(product.sku_code)}`)
  }

  return (
    <div className="mx-auto max-w-[1480px] space-y-4">
      <header className="flex flex-col gap-4 border-b pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div><p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Bestseller library</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">爆款商品库</h1><p className="mt-1 text-sm text-muted-foreground">先看图、再判断，用合适的爆款作为新品视觉参考。</p></div>
        <div className="flex gap-2"><Button variant="outline" onClick={() => void loadProducts()}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新</Button><Button onClick={() => setImportOpen(true)}><UploadCloud className="mr-2 h-4 w-4" />导入商品</Button></div>
      </header>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border bg-card/60 px-4 py-3 text-sm">
        <span><b className="tabular-nums">{summary.global_count}</b> 公共参考</span><span className="text-border">/</span><span><b className="tabular-nums">{summary.private_count}</b> 企业私有</span><span className="text-border">/</span><span className={summary.indexing_count ? 'text-amber-500' : 'text-muted-foreground'}>{summary.indexing_count} 正在索引</span>{summary.failed_count > 0 && <button onClick={() => { setIndexStatus('failed'); setPage(1) }} className="ml-auto flex items-center gap-1 text-amber-500"><AlertTriangle className="h-4 w-4" />{summary.failed_count} 个索引失败</button>}
      </div>

      <section className="space-y-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" placeholder="搜索 SKU、品类、风格或颜色" /></div>
          <div className="flex flex-wrap gap-2">
            <Select value={category} onValueChange={(value) => { setCategory(value); setPage(1) }}><SelectTrigger className="w-[130px]"><SelectValue placeholder="品类" /></SelectTrigger><SelectContent><SelectItem value="all">全部品类</SelectItem>{filters.categories.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
            <Select value={style} onValueChange={(value) => { setStyle(value); setPage(1) }}><SelectTrigger className="w-[130px]"><SelectValue placeholder="风格" /></SelectTrigger><SelectContent><SelectItem value="all">全部风格</SelectItem>{filters.styles.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
            <Select value={color} onValueChange={(value) => { setColor(value); setPage(1) }}><SelectTrigger className="w-[120px]"><SelectValue placeholder="颜色" /></SelectTrigger><SelectContent><SelectItem value="all">全部颜色</SelectItem>{filters.colors.map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select>
            <Select value={indexStatus} onValueChange={(value) => { setIndexStatus(value); setPage(1) }}><SelectTrigger className="w-[125px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem><SelectItem value="indexed">可检索</SelectItem><SelectItem value="indexing">索引中</SelectItem><SelectItem value="failed">索引失败</SelectItem></SelectContent></Select>
            <Select value={sort} onValueChange={(value) => { setSort(value); setPage(1) }}><SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="sales_desc">销量优先</SelectItem><SelectItem value="updated_desc">最近更新</SelectItem></SelectContent></Select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {([['all', '全部'], ['global', '公共参考'], ['private', '企业私有']] as const).map(([value, label]) => <Button key={value} size="sm" variant={scope === value ? 'default' : 'outline'} onClick={() => { setScope(value); setPage(1) }}>{label}</Button>)}
          <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground"><LayoutGrid className="h-3.5 w-3.5" />共 {total} 个商品</span>
        </div>
      </section>

      {loadError ? <div className="rounded-lg border border-destructive/40 p-10 text-center text-sm text-destructive">{loadError}</div> : loading ? <div className="flex min-h-80 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div> : products.length === 0 ? <div className="rounded-xl border border-dashed p-16 text-center"><ImageIcon className="mx-auto h-7 w-7 text-muted-foreground" /><p className="mt-3 font-medium">没有找到匹配的爆款商品</p><p className="mt-1 text-sm text-muted-foreground">调整筛选条件，或导入企业自己的爆款参考。</p></div> : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {products.map((product) => <button key={product.document_id} onClick={() => setSelectedProduct(product)} className="group overflow-hidden rounded-lg border bg-card text-left transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-lg hover:shadow-black/10">
            <div className="relative aspect-[4/5] overflow-hidden bg-muted">{product.image_url ? <img src={product.image_url} alt={product.sku_code} className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.025]" /> : <div className="flex h-full items-center justify-center"><ImageIcon className="h-6 w-6 text-muted-foreground" /></div>}<div className="absolute left-2 top-2 flex gap-1"><Badge variant={product.visibility === 'global' ? 'secondary' : 'outline'} className="bg-background/85 backdrop-blur">{product.visibility === 'global' ? '公共' : '企业'}</Badge>{product.index_status !== 'indexed' && <Badge variant="outline" className="border-amber-500/40 bg-background/85 text-amber-500">{indexLabel(product.index_status)}</Badge>}</div></div>
            <div className="p-3"><p className="truncate font-mono text-xs font-semibold">{product.sku_code}</p><p className="mt-1 truncate text-xs text-muted-foreground">{[product.category, product.style, product.color].filter(Boolean).join(' · ') || '未填写商品属性'}</p><p className="mt-2 text-xs tabular-nums"><span className="font-medium">{product.sales_count.toLocaleString()}</span><span className="ml-1 text-muted-foreground">销量</span></p></div>
          </button>)}
        </div>
      )}

      <div className="flex items-center justify-between border-t pt-3 text-sm text-muted-foreground"><span>第 {page} / {pageCount} 页</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="mr-1 h-4 w-4" />上一页</Button><Button variant="outline" size="sm" disabled={page >= pageCount || loading} onClick={() => setPage((value) => value + 1)}>下一页<ChevronRight className="ml-1 h-4 w-4" /></Button></div></div>

      {selectedProduct && <div className="fixed inset-0 z-50 flex justify-end"><button aria-label="关闭详情" className="absolute inset-0 bg-black/55" onClick={() => setSelectedProduct(null)} /><aside className="relative z-10 flex h-full w-full max-w-md flex-col border-l bg-background shadow-2xl"><div className="flex items-center justify-between border-b p-4"><div><p className="text-xs uppercase tracking-wider text-primary">商品详情</p><h2 className="mt-1 font-mono font-semibold">{selectedProduct.sku_code}</h2></div><Button variant="ghost" size="icon" onClick={() => setSelectedProduct(null)}><X className="h-5 w-5" /></Button></div><div className="min-h-0 flex-1 overflow-y-auto"><div className="aspect-square bg-muted">{selectedProduct.image_url ? <img src={selectedProduct.image_url} alt={selectedProduct.sku_code} className="h-full w-full object-contain" /> : null}</div><div className="space-y-5 p-5"><div className="flex flex-wrap gap-2"><Badge>{selectedProduct.visibility === 'global' ? '公共参考' : '企业私有'}</Badge><Badge variant="outline">{indexLabel(selectedProduct.index_status)}</Badge></div><div className="grid grid-cols-2 gap-4 text-sm">{[['品类', selectedProduct.category], ['风格', selectedProduct.style], ['颜色', selectedProduct.color], ['材料', selectedProduct.material], ['季节', selectedProduct.season], ['销量', selectedProduct.sales_count.toLocaleString()]].map(([label, value]) => <div key={label}><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1">{value || '—'}</p></div>)}</div><div><p className="text-xs text-muted-foreground">商品描述</p><p className="mt-2 text-sm leading-6">{selectedProduct.description || '暂无描述'}</p></div>{selectedProduct.index_error && <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><AlertTriangle className="mb-2 h-4 w-4" />{selectedProduct.index_error}</div>}</div></div><div className="space-y-2 border-t p-4"><Button className="w-full" onClick={() => createWith(selectedProduct, 'reference')}><Sparkles className="mr-2 h-4 w-4" />以此为爆款参考生成</Button><Button className="w-full" variant="outline" onClick={() => createWith(selectedProduct, 'source')}>作为新品原图生成<ArrowRight className="ml-2 h-4 w-4" /></Button><p className="text-center text-[11px] text-muted-foreground">参考商品只影响构图、灯光与氛围，不会替换新品。</p></div></aside></div>}

      <Dialog open={importOpen} onOpenChange={setImportOpen}><DialogContent className="max-w-3xl"><DialogHeader><DialogTitle>导入企业爆款商品</DialogTitle></DialogHeader><div className="grid gap-4 md:grid-cols-2"><div className="space-y-3 rounded-lg border p-4"><div className="flex items-center justify-between"><div><p className="font-medium">1. 商品表格</p><p className="text-xs text-muted-foreground">CSV、XLSX 或 XLS</p></div><FileSpreadsheet className="h-5 w-5 text-primary" /></div><input ref={catalogInputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(event) => setCatalog(event.target.files?.[0] || null)} /><Button variant="outline" className="w-full" onClick={() => catalogInputRef.current?.click()}>{catalog ? '更换表格' : '选择表格'}</Button><p className="truncate text-xs text-muted-foreground">{catalog?.name || '尚未选择文件'}</p><div className="flex gap-2"><Button asChild variant="ghost" size="sm"><a href="/templates/mediaforge-product-import-template.xlsx" download><Download className="mr-1 h-4 w-4" />Excel 模板</a></Button><Button asChild variant="ghost" size="sm"><a href="/templates/mediaforge-product-import-template.csv" download><Download className="mr-1 h-4 w-4" />CSV 模板</a></Button></div></div><div className="space-y-3 rounded-lg border p-4"><div className="flex items-center justify-between"><div><p className="font-medium">2. 商品图片</p><p className="text-xs text-muted-foreground">按表格中的文件名自动匹配</p></div><ImageIcon className="h-5 w-5 text-primary" /></div><input ref={imageInputRef} type="file" accept="image/*" multiple className="hidden" onChange={(event) => setImages(Array.from(event.target.files || []))} /><Button variant="outline" className="w-full" onClick={() => imageInputRef.current?.click()}>选择多张图片</Button><div className="flex justify-between text-xs text-muted-foreground"><span>已选择 {images.length} 张</span>{previewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : preview.length ? <span className={matchedCount === preview.length ? 'text-emerald-500' : 'text-amber-500'}>匹配 {matchedCount}/{preview.length}</span> : null}</div></div></div>{preview.length > 0 && <div className="max-h-48 overflow-y-auto rounded-lg border"><div className="sticky top-0 grid grid-cols-[1fr_1.5fr_auto] gap-3 border-b bg-background px-3 py-2 text-xs text-muted-foreground"><span>SKU</span><span>图片文件</span><span>状态</span></div>{preview.slice(0, 30).map((row) => <div key={`${row.productId}-${row.imageRef}`} className="grid grid-cols-[1fr_1.5fr_auto] gap-3 border-b px-3 py-2 text-xs last:border-0"><span className="truncate font-mono">{row.productId}</span><span className="truncate text-muted-foreground">{row.imageRef || '未填写'}</span><span className={row.matched ? 'text-emerald-500' : 'text-amber-500'}>{row.matched ? <Check className="h-4 w-4" /> : '未匹配'}</span></div>)}</div>}{importResult && <p className="flex items-center gap-2 text-sm text-emerald-500"><CheckCircle2 className="h-4 w-4" />{importResult}</p>}{importError && <p className="flex items-center gap-2 text-sm text-destructive"><AlertTriangle className="h-4 w-4" />{importError}</p>}<div className="flex items-center justify-between border-t pt-4"><p className="text-xs text-muted-foreground">图片将存入 MinIO，商品写入 PostgreSQL 并建立向量索引。</p><div className="flex gap-2"><Button variant="outline" onClick={() => setImportOpen(false)}>取消</Button><Button disabled={!catalog || previewing || !allImagesMatched || importing} onClick={handleImport}>{importing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UploadCloud className="mr-2 h-4 w-4" />}确认导入</Button></div></div></DialogContent></Dialog>
    </div>
  )
}
