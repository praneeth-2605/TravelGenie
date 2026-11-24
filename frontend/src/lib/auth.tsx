import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, type Settings, type User } from './api'

interface AuthState {
  user: User | null
  settings: Settings | null
  loading: boolean
  setSession: (s: { user: User; settings: Settings } | null) => void
  setSettings: (s: Settings) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

/** Remove this user's trips cached for offline use (shared devices, logout). */
function clearOfflineData() {
  try {
    navigator.serviceWorker?.controller?.postMessage('clear-user-data')
    if ('caches' in window) caches.delete('tg-data')
  } catch { /* not supported */ }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [loading, setLoading] = useState(true)

  const setSession = useCallback((s: { user: User; settings: Settings } | null) => {
    setUser(s?.user ?? null)
    setSettings(s?.settings ?? null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => setSession(null))
    api.me().then(setSession).catch(() => setSession(null)).finally(() => setLoading(false))
  }, [setSession])

  const logout = useCallback(async () => {
    try { await api.logout() } finally {
      setSession(null)
      clearOfflineData()
    }
  }, [setSession])

  const value = useMemo(() => ({ user, settings, loading, setSession, setSettings, logout }),
    [user, settings, loading, setSession, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** Apply the user's theme preference ('system' follows the OS). */
export function useApplyTheme(theme: Settings['theme'] | undefined) {
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const t = theme && theme !== 'system' ? theme : mq.matches ? 'dark' : 'light'
      document.documentElement.dataset.theme = t
    }
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])
}
