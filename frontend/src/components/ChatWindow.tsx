'use client'

import { useEffect, useRef, useState } from 'react'
import { Send, Loader2, Bot, User, Trash2 } from 'lucide-react'

import { api, getCsrfToken } from '@/lib/api'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

export type Message = {
  role: 'user' | 'assistant'
  content: string
}

function MessageContent({ content }: { content: string }) {
  // Split on IMAGE_GENERATED markers and bare /outputs/ paths
  // Each segment is either plain text or an image path
  const segments: { type: 'text' | 'image'; value: string }[] = []

  // Replace IMAGE_GENERATED /outputs/xxx with just /outputs/xxx so both patterns unify
  const normalized = content.replace(/IMAGE_GENERATED\s+(\/outputs\/[^\s]+)/gi, '$1')

  const parts = normalized.split(/(\/outputs\/[^\s"'\n]+\.(?:png|jpg|jpeg|webp))/gi)
  for (const part of parts) {
    if (part.match(/^\/outputs\/.+\.(?:png|jpg|jpeg|webp)$/i)) {
      segments.push({ type: 'image', value: part })
    } else if (part) {
      segments.push({ type: 'text', value: part })
    }
  }

  return (
    <div className="space-y-2">
      {segments.map((seg, i) =>
        seg.type === 'image' ? (
          <div key={i}>
            <Dialog>
              <DialogTrigger asChild>
                <button type="button" className="block cursor-zoom-in">
                  <img
                    src={seg.value}
                    alt="生成的图片"
                    className="max-w-xs rounded-lg border border-border shadow-sm transition-transform hover:scale-[1.02]"
                    loading="lazy"
                  />
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-4xl">
                <DialogHeader>
                  <DialogTitle className="font-mono text-xs break-all">
                    {seg.value}
                  </DialogTitle>
                </DialogHeader>
                <div className="flex justify-center">
                  <img
                    src={seg.value}
                    alt="生成的图片"
                    className="max-h-[75vh] w-auto rounded-md"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" size="sm" asChild>
                    <a href={seg.value} target="_blank" rel="noreferrer">
                      新窗口打开
                    </a>
                  </Button>
                  <Button variant="outline" size="sm" asChild>
                    <a href={seg.value} download>
                      下载
                    </a>
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            <div className="mt-1 text-xs text-muted-foreground break-all">{seg.value}</div>
          </div>
        ) : (
          <span key={i} className="whitespace-pre-wrap">{seg.value}</span>
        )
      )}
    </div>
  )
}

export function ChatWindow() {
  const { tenant } = useAuth()
  const sessionId = tenant?.tenant_id || 'anonymous'

  const WELCOME: Message = {
    role: 'assistant',
    content: '你好!我可以帮你生成产品图片,想做什么素材,直接告诉我吧。',
  }

  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const cleanupRef = useRef<(() => void) | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Load chat history on mount
  useEffect(() => {
    if (!tenant) return
    api
      .get<{ messages: Message[] }>(`/v1/agent/history?session_id=${sessionId}`)
      .then((res) => {
        if (res.messages && res.messages.length > 0) {
          setMessages([WELCOME, ...res.messages])
        }
      })
      .catch(() => {/* ignore, keep welcome message */})
      .finally(() => setHistoryLoaded(true))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.tenant_id])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  useEffect(() => {
    if (isStreaming) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isStreaming])

  useEffect(() => {
    return () => {
      cleanupRef.current?.()
    }
  }, [])

  const handleSubmit = () => {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setIsStreaming(true)

    let assistantContent = ''

    cleanupRef.current?.()
    cleanupRef.current = api.streamSse(
      '/v1/agent/chat',
      (data) => {
        if (data === '[DONE]') return
        assistantContent += data
        setMessages((prev) => {
          const withoutLast =
            prev[prev.length - 1]?.role === 'assistant' ? prev.slice(0, -1) : prev
          return [...withoutLast, { role: 'assistant', content: assistantContent }]
        })
      },
      () => {
        setIsStreaming(false)
      },
      (err) => {
        setIsStreaming(false)
        setError(err.message)
      },
      {
        method: 'POST',
        body: JSON.stringify({ message: text, session_id: sessionId }),
      }
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleClear = async () => {
    try {
      await fetch(`/api/v1/agent/history?session_id=${sessionId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRF-Token': getCsrfToken() ?? '' },
      })
    } catch {/* ignore */}
    setMessages([WELCOME])
    setError(null)
  }

  const thinkingLabel =
    elapsed < 5
      ? '思考中...'
      : elapsed < 30
        ? `处理中 ${elapsed}s...`
        : `生成中，请稍候 ${elapsed}s...`

  return (
    <Card className="flex h-[calc(100vh-8rem)] flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-sm font-medium">智能助手</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          disabled={isStreaming}
          className="h-7 gap-1 text-xs text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-3 w-3" />
          清空对话
        </Button>
      </div>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden p-4">
        <div className="flex-1 space-y-4 overflow-y-auto pr-2">
          {!historyLoaded && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>加载历史记录...</span>
            </div>
          )}
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
                {message.role === 'assistant' ? (
                  <Bot className="h-4 w-4" />
                ) : (
                  <User className="h-4 w-4" />
                )}
              </div>
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted'
                }`}
              >
                <MessageContent content={message.content} />
              </div>
            </div>
          ))}
          {isStreaming && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex items-center gap-1 rounded-lg bg-muted px-4 py-2 text-sm text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>{thinkingLabel}</span>
              </div>
            </div>
          )}
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}
          <div ref={scrollRef} />
        </div>

        <div className="flex gap-2 border-t border-border pt-4">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="描述你想生成什么..."
            className="min-h-0 flex-1 resize-none"
            rows={2}
            disabled={isStreaming}
          />
          <Button
            onClick={handleSubmit}
            disabled={isStreaming || !input.trim()}
            className="self-end"
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span className="sr-only">发送</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
