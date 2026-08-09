'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, Loader2 } from 'lucide-react'

import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const included = ['独立的商品与任务数据', 'Starter 工作空间', '注册后直接进入工作台']
const allowSelfSignup = process.env.NEXT_PUBLIC_ALLOW_SELF_SIGNUP === 'true'

export default function SignupPage() {
  const router = useRouter()
  const { signup, isAuthenticated, tenant, isLoading, error, clearError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (isAuthenticated && tenant) router.replace('/dashboard')
  }, [isAuthenticated, tenant, router])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLocalError(null)
    const trimmedEmail = email.trim()
    if (!displayName.trim()) {
      setLocalError('请输入名称')
      return
    }
    if (!trimmedEmail || password.length < 8) {
      setLocalError('请输入有效邮箱，密码至少 8 位')
      return
    }
    try {
      await signup(trimmedEmail, password, displayName.trim())
    } catch {
      // Auth store already contains the server error.
    }
  }

  if (!allowSelfSignup) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-4">
        <section className="w-full max-w-md rounded-xl border bg-card p-8 text-center shadow-xl">
          <h1 className="text-2xl font-semibold">公开注册已关闭</h1>
          <p className="mt-3 text-sm text-muted-foreground">请联系部署管理员创建账号后登录。</p>
          <Button asChild className="mt-6">
            <Link href="/login">返回登录</Link>
          </Button>
        </section>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-xl border bg-card shadow-2xl shadow-black/20 md:grid-cols-[0.95fr_1.05fr]">
        <aside className="hidden flex-col justify-between border-r bg-muted/20 p-10 md:flex">
          <div>
            <div className="flex h-10 w-10 items-center justify-center bg-primary font-bold text-primary-foreground">
              MF
            </div>
            <p className="mt-8 text-xs font-semibold uppercase tracking-[0.22em] text-primary">
              Start simple
            </p>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight">
              创建账号，即可开始自己的素材工作空间。
            </h1>
          </div>
          <div className="space-y-4">
            {included.map((item) => (
              <div key={item} className="flex items-center gap-3 text-sm">
                <span className="flex h-6 w-6 items-center justify-center border border-primary/40 text-primary">
                  <Check className="h-3.5 w-3.5" />
                </span>
                {item}
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
          <p className="text-sm font-medium text-primary">创建账号</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">开始使用 MediaForge</h2>
          <p className="mt-2 text-sm text-muted-foreground">注册后自动创建独立的 Starter 工作空间。</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div className="space-y-2">
              <Label htmlFor="display_name">名称</Label>
              <Input
                id="display_name"
                autoComplete="name"
                placeholder="你的名字或品牌名"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                disabled={isLoading}
              />
            </div>
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
                autoComplete="new-password"
                placeholder="至少 8 位字符"
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
              创建账号
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            已有账号？{' '}
            <Link href="/login" className="font-medium text-primary hover:underline">
              返回登录
            </Link>
          </p>
        </section>
      </div>
    </main>
  )
}
