'use client'

import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

type Option = { value: string; label: string; group?: string }

type MultiSelectProps = {
  options: Option[]
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  className?: string
}

export function MultiSelect({
  options,
  value,
  onChange,
  placeholder = '请选择',
  className,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false)

  const grouped = useMemo(() => {
    const map = new Map<string, Option[]>()
    for (const opt of options) {
      const key = opt.group ?? ''
      const arr = map.get(key) ?? []
      arr.push(opt)
      map.set(key, arr)
    }
    return Array.from(map.entries())
  }, [options])

  const labelOf = (v: string) => options.find((o) => o.value === v)?.label ?? v

  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  }

  const remove = (v: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onChange(value.filter((x) => x !== v))
  }

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        onBlur={(e) => {
          if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) {
            setOpen(false)
          }
        }}
        className="flex min-h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      >
        <div className="flex flex-1 flex-wrap gap-1">
          {value.length === 0 ? (
            <span className="text-muted-foreground">{placeholder}</span>
          ) : (
            value.map((v) => (
              <Badge key={v} variant="secondary" className="gap-1 pr-1">
                {labelOf(v)}
                <span
                  role="button"
                  onMouseDown={(e) => remove(v, e)}
                  className="ml-0.5 rounded-sm p-0.5 hover:bg-muted"
                >
                  <X className="h-3 w-3" />
                </span>
              </Badge>
            ))
          )}
        </div>
        <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
      </button>

      {open && (
        <div
          className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
          onMouseDown={(e) => e.preventDefault()}
        >
          {grouped.map(([group, opts]) => (
            <div key={group || '_'} className="py-1">
              {group && (
                <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
                  {group}
                </div>
              )}
              {opts.map((opt) => {
                const selected = value.includes(opt.value)
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => toggle(opt.value)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent',
                      selected && 'bg-accent/50',
                    )}
                  >
                    <Check
                      className={cn(
                        'h-4 w-4',
                        selected ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {opt.label}
                  </button>
                )
              })}
            </div>
          ))}
          {value.length > 0 && (
            <div className="border-t border-border p-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => onChange([])}
              >
                清空选择
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
