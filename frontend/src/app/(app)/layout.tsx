'use client'

import { useState } from 'react'
import { usePathname } from 'next/navigation'

import { Sidebar } from '@/components/Sidebar'
import { Topbar } from '@/components/Topbar'
import { cn } from '@/lib/utils'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()

  return (
    <div className="fixed inset-0 flex w-full overflow-hidden bg-background">
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar onMenuClick={() => setMobileOpen(true)} />
        <main
          className={cn(
            'min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-4 md:p-6',
            (pathname === '/batch' || pathname === '/agent')
              && 'overflow-hidden p-2 sm:p-3 md:p-4',
          )}
        >
          {children}
        </main>
      </div>
    </div>
  )
}
