import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, ApiError, setCsrfToken, setOnUnauthorized } from '@/lib/api'

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

export type User = {
  user_id: string
  tenant_id: string
  email: string
  display_name: string | null
  status: string
}

type AuthResponse = {
  user: User
  tenant: Tenant
  csrf_token: string
}

type MeResponse = { user: User; tenant: Tenant }

type AuthState = {
  isAuthenticated: boolean
  user: User | null
  tenant: Tenant | null
  csrfToken: string | null
  isLoading: boolean
  error: string | null
  hasHydrated: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, displayName?: string) => Promise<void>
  fetchMe: () => Promise<void>
  refresh: () => Promise<boolean>
  logout: () => Promise<void>
  setHasHydrated: (value: boolean) => void
  clearError: () => void
}

function applyCsrf(token: string | null) {
  setCsrfToken(token)
}

function extractMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback
  if (err instanceof Error) return err.message
  return fallback
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      user: null,
      tenant: null,
      csrfToken: null,
      isLoading: false,
      error: null,
      hasHydrated: false,
      setHasHydrated: (hasHydrated) => set({ hasHydrated }),
      clearError: () => set({ error: null }),

      login: async (email, password) => {
        set({ isLoading: true, error: null })
        try {
          const res = await api.post<AuthResponse>('/v1/auth/login', { email, password })
          applyCsrf(res.csrf_token)
          set({
            isAuthenticated: true,
            user: res.user,
            tenant: res.tenant,
            csrfToken: res.csrf_token,
            isLoading: false,
          })
        } catch (err) {
          set({ error: extractMessage(err, 'Login failed'), isLoading: false })
          throw err
        }
      },

      signup: async (email, password, displayName) => {
        set({ isLoading: true, error: null })
        try {
          const res = await api.post<AuthResponse>('/v1/auth/signup', {
            email,
            password,
            display_name: displayName ?? null,
          })
          applyCsrf(res.csrf_token)
          set({
            isAuthenticated: true,
            user: res.user,
            tenant: res.tenant,
            csrfToken: res.csrf_token,
            isLoading: false,
          })
        } catch (err) {
          set({ error: extractMessage(err, 'Signup failed'), isLoading: false })
          throw err
        }
      },

      fetchMe: async () => {
        if (get().isLoading) return
        set({ isLoading: true, error: null })
        try {
          const res = await api.get<MeResponse>('/v1/auth/me')
          set({
            isAuthenticated: true,
            user: res.user,
            tenant: res.tenant,
            isLoading: false,
          })
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            // Session truly dead → wipe local state
            applyCsrf(null)
            set({
              isAuthenticated: false,
              user: null,
              tenant: null,
              csrfToken: null,
              isLoading: false,
            })
            return
          }
          set({ error: extractMessage(err, 'Session check failed'), isLoading: false })
        }
      },

      refresh: async () => {
        try {
          // Use raw fetch — bypasses the api layer's onUnauthorized hook so
          // a failed refresh doesn't accidentally trigger a second logout call.
          const res = await fetch('/api/v1/auth/refresh', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          })
          if (!res.ok) {
            applyCsrf(null)
            set({ isAuthenticated: false, user: null, tenant: null, csrfToken: null })
            return false
          }
          const body = await res.json()
          if (body.csrf_token) {
            applyCsrf(body.csrf_token)
            set({ csrfToken: body.csrf_token })
          }
          return true
        } catch {
          applyCsrf(null)
          set({ isAuthenticated: false, user: null, tenant: null, csrfToken: null })
          return false
        }
      },

      logout: async () => {
        // Only call the backend when there's actually a session to tear down.
        // Otherwise a stale 401 from /logout would re-trigger onUnauthorized
        // and loop forever.
        const shouldCallBackend = get().isAuthenticated
        applyCsrf(null)
        set({
          isAuthenticated: false,
          user: null,
          tenant: null,
          csrfToken: null,
          error: null,
          isLoading: false,
        })
        if (shouldCallBackend) {
          try {
            await api.post('/v1/auth/logout', {})
          } catch {
            // ignore — local state already cleared
          }
        }
      },
    }),
    {
      name: 'mf-auth',
      // Never persist tokens. Only persist enough to render the shell while
      // fetchMe() revalidates the session.
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        tenant: state.tenant,
        csrfToken: state.csrfToken,
      }),
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          state?.logout?.()
          return
        }
        applyCsrf(state?.csrfToken ?? null)
        state?.setHasHydrated?.(true)
        setOnUnauthorized(() => {
          // Force-logout from anywhere in the api layer — but only if we
          // still think we're logged in, to avoid runaway loops.
          if (useAuth.getState().isAuthenticated) {
            useAuth.getState().logout()
          }
        })
        // Always revalidate session cookie on load.
        if (state?.isAuthenticated) {
          state.fetchMe?.()
        }
      },
    },
  ),
)
