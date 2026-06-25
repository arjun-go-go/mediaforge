'use client'

import { useRouter } from 'next/navigation'
import { LogOut, Menu, ImageIcon } from 'lucide-react'

import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

type TopbarProps = {
  onMenuClick: () => void
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const router = useRouter()
  const { tenant, user, logout } = useAuth()

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  const displayName = user?.display_name || user?.email || tenant?.name || '—'
  const initials = (user?.display_name || user?.email || tenant?.name || 'U')
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('') || 'U'

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
          <span className="sr-only">打开菜单</span>
        </Button>
        <h1 className="text-base font-semibold md:text-lg">MediaForge</h1>
      </div>

      <div className="flex items-center gap-3">
        {tenant && (
          <>
            <div className="hidden items-center gap-3 text-sm text-muted-foreground sm:flex">
              <span className="flex items-center gap-1">
                <ImageIcon className="h-4 w-4" />
                {tenant.quotas.image_credits_monthly}
              </span>
              {/* Video credits hidden — video generation not yet available */}
            </div>
            <Badge variant="secondary" className="hidden sm:inline-flex">
              {tenant.plan}
            </Badge>
            <div className="flex items-center gap-2 pl-2">
              <Avatar className="h-8 w-8">
                <AvatarFallback className="bg-primary text-xs text-primary-foreground">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div className="hidden flex-col md:flex">
                <span className="text-sm font-medium leading-none">{displayName}</span>
                <span className="text-xs text-muted-foreground">{tenant.name}</span>
              </div>
            </div>
          </>
        )}
        <Button variant="ghost" size="icon" onClick={handleLogout} title="退出登录">
          <LogOut className="h-4 w-4" />
          <span className="sr-only">退出登录</span>
        </Button>
      </div>
    </header>
  )
}
