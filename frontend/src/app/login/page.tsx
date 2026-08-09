'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ImageIcon, Loader2, Search, WandSparkles } from 'lucide-react'

import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const workflow = [
  { icon: ImageIcon, label: '上传商品图' },
  { icon: Search, label: '匹配爆款参考' },
  { icon: WandSparkles, label: '生成电商素材' },
]

const allowSelfSignup = process.env.NEXT_PUBLIC_ALLOW_SELF_SIGNUP === 'true'

export default function LoginPage() {
  const router = useRouter()
  const { login, isAuthenticated, tenant, isLoading, error, clearError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (isAuthenticated && tenant) router.replace('/dashboard')
  }, [isAuthenticated, tenant, router])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLocalError(null)
    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) {
      setLocalError('请输入邮箱和密码')
      return
    }
    try {
      await login(trimmedEmail, password)
    } catch {
      // Auth store already contains the server error.
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-xl border bg-card shadow-2xl shadow-black/20 md:grid-cols-[1.05fr_0.95fr]">
        <aside className="hidden flex-col justify-between border-r bg-muted/20 p-10 md:flex">
          <div>
            <div className="flex h-10 w-10 items-center justify-center bg-primary font-bold text-primary-foreground">
              MF
            </div>
            <p className="mt-8 text-xs font-semibold uppercase tracking-[0.22em] text-primary">
              MediaForge workspace
            </p>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight">
              从一张商品图，进入完整的创意生产流程。
            </h1>
          </div>
          <div className="space-y-0">
            {workflow.map(({ icon: Icon, label }, index) => (
              <div key={label} className="flex items-center gap-4 border-t py-4 last:border-b">
                <span className="font-mono text-xs text-muted-foreground">0{index + 1}</span>
                <Icon className="h-4 w-4 text-primary" />
                <span className="text-sm">{label}</span>
              </div>
            ))}
          </div>
        </aside>

        <section className="p-6 sm:p-10">
          <div className="mb-8 md:hidden">
            <div className="flex h-10 w-10 items-center justify-center bg-primary font-bold text-primary-foreground">
              MF
            </div>
          </div>
          <p className="text-sm font-medium text-primary">欢迎回来</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">登录工作空间</h2>
          <p className="mt-2 text-sm text-muted-foreground">继续管理商品库、生成任务和创意素材。</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="name@company.com"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value)
                  if (error) clearError()
                }}
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="请输入密码"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value)
                  if (error) clearError()
                }}
                disabled={isLoading}
              />
            </div>
            {(error || localError) && (
              <p className="border-l-2 border-destructive pl-3 text-sm text-destructive">
                {error || localError}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              登录
            </Button>
          </form>

          {allowSelfSignup && (
            <p className="mt-6 text-center text-sm text-muted-foreground">
              还没有账号？{' '}
              <Link href="/signup" className="font-medium text-primary hover:underline">
                免费注册
              </Link>
            </p>
          )}
        </section>
      </div>
    </main>
  )
}
