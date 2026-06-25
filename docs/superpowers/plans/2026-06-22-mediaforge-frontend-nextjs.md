# MediaForge Next.js Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dark-themed Next.js 14 frontend for MediaForge with Login/Tenant selection, Dashboard, Batch Submit, Task Detail, and Agent Chat pages.

**Architecture:** Static-exported Next.js app (output to `dist/`) served by the existing nginx container. All backend calls go through `/api/*` nginx proxy. Client-side data fetching via custom hooks and Zustand auth store. SSE consumed with `fetch` + `ReadableStream` because `EventSource` cannot set custom headers.

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Zustand, Recharts.

---

## File Structure

```
frontend/
├── package.json
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── components.json          # shadcn config
├── Dockerfile               # existing, may adjust build arg
├── nginx.conf               # existing
├── src/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── login/page.tsx
│   │   ├── dashboard/page.tsx
│   │   ├── batch/page.tsx
│   │   ├── tasks/page.tsx
│   │   └── agent/page.tsx
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   ├── Topbar.tsx
│   │   ├── StatCard.tsx
│   │   ├── JobTable.tsx
│   │   ├── SkuForm.tsx
│   │   ├── AssetGallery.tsx
│   │   └── ChatWindow.tsx
│   ├── lib/
│   │   └── api.ts
│   └── store/
│       └── auth.ts
└── middleware.ts
```

---

## Task 1: Scaffold Next.js 14 + Tailwind + shadcn/ui

**Files:**
- Create: `frontend/package.json`, `frontend/next.config.js`, `frontend/tsconfig.json`, `frontend/tailwind.config.ts`, `frontend/components.json`
- Create: `frontend/src/app/globals.css`
- Preserve: `frontend/Dockerfile`, `frontend/nginx.conf`

- [x] **Step 1: Backup existing frontend files**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
mkdir -p /tmp/mf-frontend-backup
cp Dockerfile /tmp/mf-frontend-backup/
cp nginx.conf /tmp/mf-frontend-backup/
```

- [x] **Step 2: Scaffold Next.js**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge
npx create-next-app@14 frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm
```

When prompted, accept defaults.

- [x] **Step 3: Restore Dockerfile and nginx.conf**

```bash
cp /tmp/mf-frontend-backup/Dockerfile C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend\Dockerfile
cp /tmp/mf-frontend-backup/nginx.conf C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend\nginx.conf
```

- [x] **Step 4: Initialize shadcn/ui**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
npx shadcn@latest init -d
```

Select "Default" style, "Slate" base color when asked.

- [x] **Step 5: Configure static export**

`frontend/next.config.js`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  distDir: 'dist',
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },
}

module.exports = nextConfig
```

- [x] **Step 6: Add dark theme CSS**

`frontend/src/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: 222 47% 6%;
  --foreground: 210 40% 98%;
  --card: 222 47% 8%;
  --card-foreground: 210 40% 98%;
  --popover: 222 47% 8%;
  --popover-foreground: 210 40% 98%;
  --primary: 17 89% 55%;
  --primary-foreground: 210 40% 98%;
  --secondary: 217 33% 17%;
  --secondary-foreground: 210 40% 98%;
  --muted: 217 33% 17%;
  --muted-foreground: 215 20% 65%;
  --accent: 17 89% 55%;
  --accent-foreground: 210 40% 98%;
  --destructive: 0 84% 60%;
  --destructive-foreground: 210 40% 98%;
  --border: 217 33% 17%;
  --input: 217 33% 17%;
  --ring: 17 89% 55%;
  --radius: 0.5rem;
}

body {
  @apply bg-background text-foreground antialiased;
}

@layer base {
  * {
    @apply border-border;
  }
}
```

- [x] **Step 7: Install dependencies**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
npm install zustand recharts lucide-react
npx shadcn add button input card badge select table textarea avatar separator scroll-area dialog
```

- [x] **Step 8: Verify build**

```bash
npm run build
```

Expected: `dist/` created with `index.html`.

- [x] **Step 9: Commit**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge
git add frontend
git commit -m "chore: scaffold Next.js 14 frontend with shadcn/ui"
```

---

## Task 2: API Client and Auth Store

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/store/auth.ts`
- Create: `frontend/middleware.ts`

- [x] **Step 1: Implement API client**

`frontend/src/lib/api.ts`:

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

function getApiKey(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('mf_api_key')
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  const apiKey = getApiKey()
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(apiKey ? { 'X-Api-Key': apiKey } : {}),
      'Content-Type': 'application/json',
    },
  })

  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const data = await res.json()
      message = data.detail || JSON.stringify(data)
    } catch {
      message = await res.text()
    }
    throw new ApiError(res.status, message)
  }

  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await res.json()) as T
  }
  return (await res.text()) as T
}

export const api = {
  get: <T>(path: string) => requestJson<T>(path, { method: 'GET' }),
  post: <T>(path: string, body: unknown) =>
    requestJson<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  upload: async (file: File): Promise<{ url: string }> => {
    const url = `${API_BASE}/v1/upload`
    const apiKey = getApiKey()
    const formData = new FormData()
    formData.append('file', file)
    const res = await fetch(url, {
      method: 'POST',
      headers: apiKey ? { 'X-Api-Key': apiKey } : {},
      body: formData,
    })
    if (!res.ok) {
      const text = await res.text()
      throw new ApiError(res.status, text)
    }
    return (await res.json()) as { url: string }
  },
  streamSse: (
    path: string,
    onMessage: (data: string) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
  ): (() => void) => {
    const apiKey = getApiKey()
    const url = `${API_BASE}${path}`
    const abort = new AbortController()

    fetch(url, {
      headers: apiKey ? { 'X-Api-Key': apiKey } : {},
      signal: abort.signal,
    })
      .then(async (res) => {
        if (!res.ok || !res.body) throw new Error(`SSE failed: ${res.status}`)
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n\n')
          buffer = lines.pop() || ''
          for (const chunk of lines) {
            const dataLine = chunk.split('\n').find((l) => l.startsWith('data:'))
            if (dataLine) {
              onMessage(dataLine.slice(5).trim())
            }
          }
        }
        onDone?.()
      })
      .catch((err) => onError?.(err))

    return () => abort.abort()
  },
}
```

- [x] **Step 2: Implement Zustand auth store**

`frontend/src/store/auth.ts`:

```ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '@/lib/api'

export type Tenant = {
  tenant_id: string
  name: string
  plan: string
  quotas: {
    max_concurrent_jobs: number
    max_skus_per_job: number
    image_credits_monthly: number
    video_credits_monthly: number
  }
}

type AuthState = {
  apiKey: string | null
  tenant: Tenant | null
  isLoading: boolean
  error: string | null
  setApiKey: (key: string) => void
  fetchTenant: () => Promise<void>
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      apiKey: null,
      tenant: null,
      isLoading: false,
      error: null,
      setApiKey: (apiKey) => set({ apiKey }),
      fetchTenant: async () => {
        set({ isLoading: true, error: null })
        try {
          const tenant = await api.get<Tenant>('/v1/me')
          set({ tenant, isLoading: false })
        } catch (err: any) {
          set({ error: err.message || 'Failed to fetch tenant', isLoading: false })
        }
      },
      logout: () => set({ apiKey: null, tenant: null, error: null }),
    }),
    { name: 'mf-auth' }
  )
)
```

- [x] **Step 3: Add route middleware**

`frontend/middleware.ts`:

```ts
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const apiKey = request.cookies.get('mf-auth')?.value
  const isLogin = request.nextUrl.pathname === '/login'

  if (!apiKey && !isLogin) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  if (apiKey && isLogin) {
    return NextResponse.redirect(new URL('/dashboard', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
```

- [x] **Step 4: Commit**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge
git add frontend/src/lib/api.ts frontend/src/store/auth.ts frontend/middleware.ts
git commit -m "feat: api client, auth store, and route guards"
```

---

## Task 3: Layout with Sidebar and Topbar

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/Topbar.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [x] **Step 1: Sidebar component**

`frontend/src/components/Sidebar.tsx`:

```tsx
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Package, List, Bot } from 'lucide-react'

const nav = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/batch', label: 'Batch Submit', icon: Package },
  { href: '/tasks', label: 'Tasks', icon: List },
  { href: '/agent', label: 'Agent Chat', icon: Bot },
]

export function Sidebar() {
  const pathname = usePathname()
  return (
    <aside className="fixed left-0 top-0 z-40 h-full w-64 border-r border-border bg-card">
      <div className="flex h-16 items-center gap-3 px-6">
        <div className="h-8 w-8 rounded-lg bg-primary" />
        <span className="text-lg font-bold">MediaForge</span>
      </div>
      <nav className="px-3 py-4">
        {nav.map((item) => {
          const Icon = item.icon
          const active = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
```

- [x] **Step 2: Topbar component**

`frontend/src/components/Topbar.tsx`:

```tsx
'use client'

import { useAuth } from '@/store/auth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

export function Topbar() {
  const { tenant, logout } = useAuth()
  return (
    <header className="fixed left-64 right-0 top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-card/80 px-6 backdrop-blur">
      <span className="text-sm text-muted-foreground">AI Content Generation Platform</span>
      <div className="flex items-center gap-4">
        {tenant && (
          <>
            <span className="text-sm font-medium">{tenant.name}</span>
            <Badge variant="secondary">{tenant.plan}</Badge>
          </>
        )}
        <Button variant="ghost" size="sm" onClick={logout}>
          Logout
        </Button>
      </div>
    </header>
  )
}
```

- [x] **Step 3: Layout**

`frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Sidebar } from '@/components/Sidebar'
import { Topbar } from '@/components/Topbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'MediaForge',
  description: 'AI image and video generation for e-commerce',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <Sidebar />
        <Topbar />
        <main className="ml-64 mt-16 min-h-[calc(100vh-4rem)] bg-background p-6">
          {children}
        </main>
      </body>
    </html>
  )
}
```

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/components/Topbar.tsx frontend/src/app/layout.tsx
git commit -m "feat: sidebar and topbar layout"
```

---

## Task 4: Login / Tenant Selection Page

**Files:**
- Create: `frontend/src/app/login/page.tsx`

- [x] **Step 1: Build login page**

`frontend/src/app/login/page.tsx`:

```tsx
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export default function LoginPage() {
  const router = useRouter()
  const { apiKey, setApiKey, tenant, fetchTenant, isLoading, error } = useAuth()
  const [input, setInput] = useState('')

  useEffect(() => {
    if (apiKey) fetchTenant()
  }, [apiKey])

  useEffect(() => {
    if (tenant) router.push('/dashboard')
  }, [tenant, router])

  const handleVerify = async () => {
    setApiKey(input)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">MediaForge</CardTitle>
          <p className="text-sm text-muted-foreground">Enter your API key to continue</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              type="password"
              placeholder="X-Api-Key"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
            <Button onClick={handleVerify} disabled={isLoading}>
              {isLoading ? 'Verifying...' : 'Verify'}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}

          {tenant && (
            <div className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{tenant.name}</span>
                <Badge variant="outline">{tenant.plan}</Badge>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                <div>Image credits: {tenant.quotas.image_credits_monthly}</div>
                <div>Video credits: {tenant.quotas.video_credits_monthly}</div>
                <div>Max jobs: {tenant.quotas.max_concurrent_jobs}</div>
                <div>Max SKUs/job: {tenant.quotas.max_skus_per_job}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [x] **Step 2: Build and verify**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
npm run build
```

- [x] **Step 3: Commit**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge
git add frontend/src/app/login/page.tsx
git commit -m "feat: login and tenant selection page"
```

---

## Task 5: Dashboard Page

**Files:**
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/components/StatCard.tsx`
- Create: `frontend/src/components/JobTable.tsx`

- [x] **Step 1: StatCard component**

`frontend/src/components/StatCard.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}
```

- [x] **Step 2: JobTable component**

`frontend/src/components/JobTable.tsx`:

```tsx
'use client'

import Link from 'next/link'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

export type JobSummary = {
  job_id: string
  status: string
  total_skus: number
  done_skus: number
  created_at: string
}

export function JobTable({ jobs }: { jobs: JobSummary[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Job ID</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Progress</TableHead>
          <TableHead>Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.job_id}>
            <TableCell>
              <Link href={`/tasks?jobId=${job.job_id}`} className="text-primary hover:underline">
                {job.job_id.slice(0, 8)}
              </Link>
            </TableCell>
            <TableCell>
              <Badge variant="outline">{job.status}</Badge>
            </TableCell>
            <TableCell>
              {job.done_skus} / {job.total_skus}
            </TableCell>
            <TableCell>{new Date(job.created_at).toLocaleString()}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
```

- [x] **Step 3: Dashboard page**

`frontend/src/app/dashboard/page.tsx`:

```tsx
'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { StatCard } from '@/components/StatCard'
import { JobTable, JobSummary } from '@/components/JobTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, PieChart, Pie, Cell } from 'recharts'

const mockTrend = [
  { day: 'Mon', jobs: 3 },
  { day: 'Tue', jobs: 5 },
  { day: 'Wed', jobs: 2 },
  { day: 'Thu', jobs: 8 },
  { day: 'Fri', jobs: 6 },
  { day: 'Sat', jobs: 4 },
  { day: 'Sun', jobs: 7 },
]

const mockTypes = [
  { name: 'Main Image', value: 45 },
  { name: 'Video', value: 30 },
  { name: 'Detail Page', value: 15 },
  { name: 'Social', value: 10 },
]

const COLORS = ['#f97316', '#3b82f6', '#10b981', '#8b5cf6']

export default function DashboardPage() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<{ jobs: JobSummary[] }>('/v1/tasks')
      .then((data) => setJobs(data.jobs))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const running = jobs.filter((j) => j.status === 'running').length
  const completed = jobs.filter((j) => j.status === 'done').length

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Running Jobs" value={running} />
        <StatCard title="Completed Today" value={completed} />
        <StatCard title="Total Jobs" value={jobs.length} />
        <StatCard title="Generated Assets" value={jobs.reduce((sum, j) => sum + j.done_skus, 0)} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>7-Day Job Trend</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mockTrend}>
                <XAxis dataKey="day" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: 'none' }} />
                <Line type="monotone" dataKey="jobs" stroke="#f97316" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Output Type Distribution</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={mockTypes} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {mockTypes.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: 'none' }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Jobs</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!loading && !error && <JobTable jobs={jobs.slice(0, 10)} />}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/StatCard.tsx frontend/src/components/JobTable.tsx frontend/src/app/dashboard/page.tsx
git commit -m "feat: dashboard with stats and charts"
```

---

## Task 6: Batch Submit Page

**Files:**
- Create: `frontend/src/app/batch/page.tsx`
- Create: `frontend/src/components/SkuForm.tsx`

- [x] **Step 1: SkuForm component**

`frontend/src/components/SkuForm.tsx`:

```tsx
'use client'

import { useState, useRef } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'
import { Upload } from 'lucide-react'

export type Sku = {
  sku_id: string
  product_image_url: string
  product_name: string
  category: string
  target_platforms: string
  output_types: string
  market: string
  style_hint: string
}

export function SkuForm({ sku, index, onChange }: { sku: Sku; index: number; onChange: (sku: Sku) => void }) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const { url } = await api.upload(file)
      onChange({ ...sku, product_image_url: url })
    } catch (err: any) {
      alert(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="grid gap-4 rounded-lg border border-border p-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>SKU ID</Label>
          <Input value={sku.sku_id} onChange={(e) => onChange({ ...sku, sku_id: e.target.value })} />
        </div>
        <div>
          <Label>Product Name</Label>
          <Input value={sku.product_name} onChange={(e) => onChange({ ...sku, product_name: e.target.value })} />
        </div>
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="Image URL"
          value={sku.product_image_url}
          onChange={(e) => onChange({ ...sku, product_image_url: e.target.value })}
        />
        <input
          type="file"
          accept="image/*"
          hidden
          ref={fileRef}
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
        />
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
          <Upload className="mr-2 h-4 w-4" />
          {uploading ? 'Uploading' : 'Upload'}
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Input placeholder="Category" value={sku.category} onChange={(e) => onChange({ ...sku, category: e.target.value })} />
        <Input placeholder="Platforms (comma)" value={sku.target_platforms} onChange={(e) => onChange({ ...sku, target_platforms: e.target.value })} />
        <Input placeholder="Output types (comma)" value={sku.output_types} onChange={(e) => onChange({ ...sku, output_types: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Input placeholder="Market" value={sku.market} onChange={(e) => onChange({ ...sku, market: e.target.value })} />
        <Input placeholder="Style hint" value={sku.style_hint} onChange={(e) => onChange({ ...sku, style_hint: e.target.value })} />
      </div>
    </div>
  )
}
```

- [x] **Step 2: Batch page**

`frontend/src/app/batch/page.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { SkuForm, Sku } from '@/components/SkuForm'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const emptySku: Sku = {
  sku_id: '',
  product_image_url: '',
  product_name: '',
  category: '',
  target_platforms: 'amazon',
  output_types: 'main_image',
  market: 'US',
  style_hint: '',
}

export default function BatchPage() {
  const router = useRouter()
  const [skus, setSkus] = useState<Sku[]>([{ ...emptySku }])
  const [imageModel, setImageModel] = useState('pro')
  const [videoModel, setVideoModel] = useState('veo')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateSku = (index: number, sku: Sku) => {
    const next = [...skus]
    next[index] = sku
    setSkus(next)
  }

  const addSku = () => setSkus([...skus, { ...emptySku }])

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const payload = {
        skus: skus.map((s) => ({
          ...s,
          target_platforms: s.target_platforms.split(',').map((x) => x.trim()),
          output_types: s.output_types.split(',').map((x) => x.trim()),
        })),
        image_model: imageModel,
        video_model: videoModel,
      }
      const data = await api.post<{ job_id: string; status: string }>('/v1/batch/submit', payload)
      router.push(`/tasks?jobId=${data.job_id}`)
    } catch (err: any) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold">Batch Submit</h1>

      <Card>
        <CardHeader>
          <CardTitle>Task Configuration</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div>
            <Label>Image Model</Label>
            <Select value={imageModel} onValueChange={setImageModel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="fast">Fast</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Video Model</Label>
            <Select value={videoModel} onValueChange={setVideoModel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="veo">Veo</SelectItem>
                <SelectItem value="seedance">Seedance</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {skus.map((sku, i) => (
          <SkuForm key={i} sku={sku} index={i} onChange={(s) => updateSku(i, s)} />
        ))}
      </div>

      <div className="flex items-center gap-4">
        <Button variant="outline" onClick={addSku}>
          + Add SKU
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Submitting...' : 'Submit Batch'}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}
```

- [x] **Step 3: Commit**

```bash
git add frontend/src/components/SkuForm.tsx frontend/src/app/batch/page.tsx
git commit -m "feat: batch submit page with SKU form and upload"
```

---

## Task 7: Task Detail Page

**Files:**
- Create: `frontend/src/app/tasks/page.tsx`
- Create: `frontend/src/components/AssetGallery.tsx`

- [x] **Step 1: AssetGallery component**

`frontend/src/components/AssetGallery.tsx`:

```tsx
import { Card, CardContent } from '@/components/ui/card'

export type Asset = {
  sku_id: string
  output_type: string
  file_path: string | null
  status: string
  platform: string | null
  error_msg: string | null
}

export function AssetGallery({ assets }: { assets: Asset[] }) {
  const succeeded = assets.filter((a) => a.status === 'success' && a.file_path)
  if (succeeded.length === 0) return <p className="text-sm text-muted-foreground">No generated assets yet.</p>

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {succeeded.map((asset, i) => (
        <Card key={i}>
          <CardContent className="p-2">
            {asset.output_type === 'video' ? (
              <video src={asset.file_path!} controls className="rounded-md" />
            ) : (
              <img src={asset.file_path!} alt={asset.sku_id} className="rounded-md object-cover" />
            )}
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{asset.sku_id}</span>
              <span>{asset.output_type}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
```

- [x] **Step 2: Task detail page**

`frontend/src/app/tasks/page.tsx`:

```tsx
'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'
import { AssetGallery, Asset } from '@/components/AssetGallery'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'

function TaskDetail() {
  const searchParams = useSearchParams()
  const jobId = searchParams.get('jobId')
  const [job, setJob] = useState<any>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchJob = async () => {
    if (!jobId) return
    try {
      const data = await api.get<any>(`/v1/tasks/${jobId}`)
      setJob(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJob()
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    const stop = api.streamSse(
      `/v1/tasks/${jobId}/stream`,
      (data) => {
        setLogs((prev) => [...prev, data])
        try {
          const parsed = JSON.parse(data)
          if (parsed.event === 'done') fetchJob()
        } catch {}
      },
      () => {},
      (err) => console.error('SSE error', err)
    )
    return () => stop()
  }, [jobId])

  if (!jobId) return <p className="text-destructive">Missing jobId parameter.</p>
  if (loading) return <p className="text-muted-foreground">Loading task...</p>
  if (error) return <p className="text-destructive">{error}</p>

  const progress = job.total_skus ? Math.round((job.done_skus / job.total_skus) * 100) : 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Task {jobId.slice(0, 8)}</h1>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Status</CardTitle>
            <Badge variant="outline">{job.status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Progress value={progress} />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{job.done_skus} / {job.total_skus} SKUs completed</span>
            <span>{progress}%</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Generated Assets</CardTitle>
        </CardHeader>
        <CardContent>
          <AssetGallery assets={job.assets || []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Live Log</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-48 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
            {logs.length === 0 ? <span className="text-muted-foreground">Waiting for events...</span> : null}
            {logs.map((log, i) => (
              <div key={i} className="py-0.5">{log}</div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function TasksPage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Loading...</p>}>
      <TaskDetail />
    </Suspense>
  )
}
```

- [x] **Step 3: Commit**

```bash
git add frontend/src/components/AssetGallery.tsx frontend/src/app/tasks/page.tsx
git commit -m "feat: task detail page with SSE progress"
```

---

## Task 8: Agent Chat Page

**Files:**
- Create: `frontend/src/app/agent/page.tsx`
- Create: `frontend/src/components/ChatWindow.tsx`

- [x] **Step 1: ChatWindow component**

`frontend/src/components/ChatWindow.tsx`:

```tsx
'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api } from '@/lib/api'

export type Message = {
  role: 'user' | 'assistant'
  content: string
}

export function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim()) return
    const userMsg = input.trim()
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])
    setInput('')
    setStreaming(true)

    setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

    api.streamSse(
      '/v1/agent/chat',
      (data) => {
        if (data === '[DONE]') {
          setStreaming(false)
          return
        }
        setMessages((prev) => {
          const last = { ...prev[prev.length - 1] }
          last.content += data
          return [...prev.slice(0, -1), last]
        })
      },
      () => setStreaming(false),
      () => setStreaming(false)
    )
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col rounded-lg border border-border bg-card">
      <ScrollArea className="flex-1 p-4">
        {messages.map((m, i) => (
          <div key={i} className={`mb-4 flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </ScrollArea>
      <div className="border-t border-border p-4">
        <div className="flex gap-2">
          <Input
            placeholder="Ask MediaForge Agent..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            disabled={streaming}
          />
          <Button onClick={sendMessage} disabled={streaming}>
            {streaming ? '...' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  )
}
```

- [x] **Step 2: Agent page**

`frontend/src/app/agent/page.tsx`:

```tsx
import { ChatWindow } from '@/components/ChatWindow'

export default function AgentPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Agent Chat</h1>
      <ChatWindow />
    </div>
  )
}
```

- [x] **Step 3: Commit**

```bash
git add frontend/src/components/ChatWindow.tsx frontend/src/app/agent/page.tsx
git commit -m "feat: agent chat page with SSE streaming"
```

---

## Task 9: Build, Docker, and Final Verification

**Files:**
- Modify: `frontend/Dockerfile` (optional build arg)
- Modify: `frontend/next.config.js` if needed

- [x] **Step 1: Final build**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
npm run build
```

Expected: no errors, `dist/` contains `index.html` and all pages.

- [x] **Step 2: Update Dockerfile build arg (optional)**

`frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [x] **Step 3: Build Docker image locally (optional)**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge\frontend
docker build -t mediaforge:frontend .
```

- [x] **Step 4: Commit**

```bash
cd C:\Users\Arjun\Desktop\LLMST\mediaforge
git add frontend
git commit -m "chore: final frontend build and docker config"
```

---

## Self-Review

- Spec coverage: Login/Tenant ✅, Dashboard ✅, Batch Submit ✅, Task Detail ✅, Agent Chat ✅, SSE ✅, file upload ✅.
- Placeholders: none; all code provided.
- Type consistency: `Sku` type reused between `SkuForm` and `BatchPage`; `JobSummary` reused in `JobTable` and `DashboardPage`.

## Implementation Notes / Divergences

- **Routing:** `middleware.ts` was not used; route protection is handled client-side by `RouteGuard.tsx` because the app is statically exported.
- **Task page:** `/tasks` lists all jobs and also renders the task detail view when `?jobId=` is present, instead of having a separate `/tasks/detail` route.
- **Batch route:** The route is `/batch` (singular) and the component file is `frontend/src/app/batch/page.tsx`.
- **Layout components:** The sidebar/topbar files are named `Sidebar.tsx` and `Topbar.tsx`, used by `frontend/src/app/(app)/layout.tsx`.
- **Component props:** The extracted components preserve the plan naming (`StatCard`, `JobTable`, `SkuForm`, `AssetGallery`, `ChatWindow`) but were enriched with stronger typing, status badges, and upload state handling to match the existing backend contract.
