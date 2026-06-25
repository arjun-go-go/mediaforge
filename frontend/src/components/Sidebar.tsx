'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Package, ClipboardList, MessageSquare, Settings, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const nav = [
  { name: '工作台', href: '/dashboard', icon: LayoutDashboard },
  { name: '批量提交', href: '/batch', icon: Package },
  { name: '任务列表', href: '/tasks', icon: ClipboardList },
  { name: '智能助手', href: '/agent', icon: MessageSquare },
  { name: '设置', href: '/settings/api-keys', icon: Settings },
]

type SidebarProps = {
  mobileOpen: boolean
  onClose: () => void
}

export function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const pathname = usePathname()

  const sidebar = (
    <div className="flex h-full w-64 flex-col border-r border-border bg-card">
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
          MF
        </div>
        <span className="text-lg font-semibold">MediaForge</span>
        <Button variant="ghost" size="icon" className="ml-auto md:hidden" onClick={onClose}>
          <X className="h-5 w-5" />
          <span className="sr-only">关闭菜单</span>
        </Button>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {nav.map((item) => {
          const Icon = item.icon
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
          return (
            <Link key={item.href} href={item.href} onClick={onClose}>
              <span
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.name}
              </span>
            </Link>
          )
        })}
      </nav>
    </div>
  )

  return (
    <>
      <aside className="hidden md:flex md:flex-col">{sidebar}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="fixed inset-0 bg-black/50" onClick={onClose} />
          <div className="relative z-50 flex h-full">{sidebar}</div>
        </div>
      )}
    </>
  )
}
