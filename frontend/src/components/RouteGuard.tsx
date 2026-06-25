'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/store/auth'
import { Loading } from '@/components/Loading'
import { Button } from '@/components/ui/button'

const publicPaths = ['/login', '/signup']

export function RouteGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { isAuthenticated, tenant, hasHydrated, isLoading } = useAuth()
  const [mounted, setMounted] = useState(false)
  const isPublic = publicPaths.includes(pathname)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted || !hasHydrated) return
    if (isAuthenticated && isPublic) {
      router.replace('/dashboard')
    }
    if (!isAuthenticated && !isPublic) {
      router.replace('/login')
    }
  }, [isAuthenticated, isPublic, hasHydrated, mounted, router])

  if (isPublic) {
    if (isAuthenticated) return <Loading />
    return <>{children}</>
  }

  if (!mounted || !hasHydrated || isLoading) {
    return <Loading />
  }

  if (!isAuthenticated || !tenant) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background p-4 text-center">
        <p className="text-destructive">需要身份验证</p>
        <Button onClick={() => router.replace('/login')}>前往登录</Button>
      </div>
    )
  }

  return <>{children}</>
}
