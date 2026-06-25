const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

export class ApiError extends Error {
  code: string | null
  constructor(public status: number, message: string, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

// Module-level state shared across all api.* calls.
let csrfToken: string | null = null
let refreshInflight: Promise<boolean> | null = null
let onUnauthorized: (() => void) | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export function getCsrfToken(): string | null {
  return csrfToken
}

/**
 * Register a callback invoked when a refresh also fails (session truly dead).
 * The frontend uses this to force-logout the user.
 */
export function setOnUnauthorized(cb: (() => void) | null) {
  onUnauthorized = cb
}

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null
  const name = 'mf_csrf='
  const parts = document.cookie.split(';')
  for (const p of parts) {
    const trimmed = p.trim()
    if (trimmed.indexOf(name) === 0) return decodeURIComponent(trimmed.substring(name.length))
  }
  return null
}

function timeoutSignal(
  signal: AbortSignal | null | undefined,
  ms: number,
): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController()
  const timer = setTimeout(
    () => controller.abort(new DOMException('Request timeout', 'TimeoutError')),
    ms,
  )

  let onAbort: (() => void) | undefined
  const clear = () => {
    clearTimeout(timer)
    if (signal && onAbort) {
      signal.removeEventListener('abort', onAbort)
    }
  }
  if (signal) {
    if (signal.aborted) {
      controller.abort(signal.reason)
      return { signal: controller.signal, clear }
    }
    onAbort = () => controller.abort(signal.reason)
    signal.addEventListener('abort', onAbort, { once: true })
  }
  return { signal: controller.signal, clear }
}

function isStateChanging(method: string): boolean {
  const m = method.toUpperCase()
  return m !== 'GET' && m !== 'HEAD' && m !== 'OPTIONS'
}

function buildHeaders(
  method: string,
  callerHeaders: HeadersInit | undefined,
  body: BodyInit | null | undefined,
): Headers {
  const headers = new Headers()
  const incoming = new Headers(callerHeaders || {})
  incoming.forEach((value, key) => {
    const lower = key.toLowerCase()
    if (lower !== 'content-type' && lower !== 'x-csrf-token') {
      headers.set(key, value)
    }
  })

  const isFormData = body instanceof FormData
  if (body && !isFormData) headers.set('Content-Type', 'application/json')

  if (isStateChanging(method)) {
    const token = csrfToken ?? readCsrfCookie()
    if (token) headers.set('X-CSRF-Token', token)
  }
  return headers
}

async function parseError(res: Response): Promise<ApiError> {
  const text = await res.text()
  let message = `HTTP ${res.status}`
  let code: string | null = null
  try {
    const data = JSON.parse(text)
    if (data.detail) {
      if (typeof data.detail === 'string') {
        message = data.detail
      } else if (typeof data.detail === 'object') {
        message = data.detail.msg || JSON.stringify(data.detail)
        code = data.detail.code || null
      }
    } else if (data.message) {
      message = data.message
    }
  } catch {
    message = text || message
  }
  return new ApiError(res.status, message, code)
}

/**
 * Attempt a single silent refresh. Concurrent 401s share the same promise.
 * Returns true if refresh succeeded, false otherwise.
 */
async function attemptRefresh(): Promise<boolean> {
  if (refreshInflight) return refreshInflight
  refreshInflight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: buildHeaders('POST', undefined, null),
      })
      if (!res.ok) return false
      const body = await res.json()
      if (body.csrf_token) setCsrfToken(body.csrf_token)
      return true
    } catch {
      return false
    } finally {
      refreshInflight = null
    }
  })()
  return refreshInflight
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  retried = false,
): Promise<T> {
  const url = `${API_BASE}${path}`
  const method = options.method || 'GET'
  const headers = buildHeaders(method, options.headers, options.body)
  const { signal, clear } = timeoutSignal(options.signal, 30000)
  try {
    const res = await fetch(url, {
      ...options,
      method,
      signal,
      headers,
      credentials: 'include',
    })

    if (res.status === 401 && !retried) {
      const err = await parseError(res)
      if (err.code === 'token_expired' || err.code === 'missing_credentials') {
        const refreshed = await attemptRefresh()
        if (refreshed) {
          return requestJson<T>(path, options, true)
        }
      }
      onUnauthorized?.()
      throw err
    }

    if (!res.ok) {
      throw await parseError(res)
    }

    const contentType = res.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      return (await res.json()) as T
    }
    return (await res.text()) as T
  } finally {
    clear()
  }
}

async function requestFormData<T>(
  path: string,
  file: File,
  timeoutMs: number,
  retried = false,
): Promise<T> {
  const url = `${API_BASE}${path}`
  const formData = new FormData()
  formData.append('file', file)
  const headers = buildHeaders('POST', undefined, formData)
  const { signal, clear } = timeoutSignal(undefined, timeoutMs)
  try {
    const res = await fetch(url, {
      method: 'POST',
      signal,
      headers,
      body: formData,
      credentials: 'include',
    })

    if (res.status === 401 && !retried) {
      const err = await parseError(res)
      if (err.code === 'token_expired' || err.code === 'missing_credentials') {
        const refreshed = await attemptRefresh()
        if (refreshed) return requestFormData<T>(path, file, timeoutMs, true)
      }
      onUnauthorized?.()
      throw err
    }

    if (!res.ok) {
      throw await parseError(res)
    }
    return (await res.json()) as T
  } finally {
    clear()
  }
}

export const api = {
  get: <T>(path: string) => requestJson<T>(path, { method: 'GET' }),
  post: <T>(path: string, body: unknown) =>
    requestJson<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  delete: <T>(path: string) => requestJson<T>(path, { method: 'DELETE' }),
  upload: (file: File) => requestFormData<{ url: string }>('/v1/upload', file, 120000),
  ingestCsv: (file: File) =>
    requestFormData<{ accepted: number; message: string }>('/v1/rag/ingest', file, 60000),
  ragStatus: () =>
    requestJson<{ status: string; count: number; backend: string }>('/v1/rag/status'),
  streamSse: (
    path: string,
    onMessage: (data: string) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
    options: {
      method?: string
      body?: BodyInit
      query?: Record<string, string>
      signal?: AbortSignal
    } = {},
  ): (() => void) => {
    const method = options.method || 'GET'
    const query = options.query ? '?' + new URLSearchParams(options.query).toString() : ''
    const url = `${API_BASE}${path}${query}`
    const abort = new AbortController()
    if (options.signal) {
      if (options.signal.aborted) {
        abort.abort(options.signal.reason)
      } else {
        options.signal.addEventListener('abort', () => abort.abort(options.signal?.reason), {
          once: true,
        })
      }
    }

    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    const contentType =
      options.body && !(options.body instanceof FormData) ? 'application/json' : undefined
    if (contentType) headers['Content-Type'] = contentType
    if (isStateChanging(method)) {
      const token = csrfToken ?? readCsrfCookie()
      if (token) headers['X-CSRF-Token'] = token
    }

    fetch(url, {
      method,
      body: options.body,
      signal: abort.signal,
      headers,
      credentials: 'include',
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
            const dataLines = chunk.split('\n').filter((l) => l.startsWith('data:'))
            if (dataLines.length) {
              onMessage(dataLines.map((l) => l.slice(5).trim()).join('\n'))
            }
          }
        }
        onDone?.()
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        onError?.(err)
      })

    return () => abort.abort()
  },
}
