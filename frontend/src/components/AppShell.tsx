import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Database, Download, LayoutDashboard, LogOut, Menu, Plus, Settings as SettingsIcon, Star, WifiOff, X } from 'lucide-react'
import { api, type TripSummary } from '../lib/api'
import { useAuth } from '../lib/auth'

interface TripsCtx {
  trips: TripSummary[]
  loaded: boolean
  refresh: () => Promise<void>
}
const TripsContext = createContext<TripsCtx>({ trips: [], loaded: false, refresh: async () => {} })
export const useTrips = () => useContext(TripsContext)

export function Avatar({ name, url, className = 'size-8 text-xs' }: { name: string; url?: string | null; className?: string }) {
  const initials = name.split(/\s+/).map(p => p[0]).join('').slice(0, 2).toUpperCase()
  const cls = `${className} shrink-0 rounded-full`
  return url
    ? <img src={url} alt="" className={cls} referrerPolicy="no-referrer" />
    : <span className={`${cls} grid place-items-center bg-accent font-semibold text-accent-ink`}>{initials}</span>
}

function NavItem({ to, icon: Icon, children, end }: { to: string; icon: typeof Plus; children: ReactNode; end?: boolean }) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition ${isActive ? 'bg-surface-2 font-medium text-ink' : 'text-muted hover:bg-surface-2/70 hover:text-ink'}`}>
      <Icon className="size-4" /> {children}
    </NavLink>
  )
}

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** Offers "Install app" where the browser supports it (Chrome / Edge / Android). */
function useInstallPrompt() {
  const [event, setEvent] = useState<InstallPromptEvent | null>(null)
  useEffect(() => {
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallPromptEvent) }
    const onInstalled = () => setEvent(null)
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => { window.removeEventListener('beforeinstallprompt', onPrompt); window.removeEventListener('appinstalled', onInstalled) }
  }, [])
  const install = async () => {
    if (!event) return
    await event.prompt()
    await event.userChoice
    setEvent(null)
  }
  return { canInstall: !!event, install }
}

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down) }
  }, [])
  return online
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [loaded, setLoaded] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { canInstall, install } = useInstallPrompt()
  const online = useOnline()

  const refresh = useCallback(async () => {
    try { setTrips(await api.trips()) } catch { /* handled by 401 handler */ } finally { setLoaded(true) }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  if (!user) return null
  const recent = [...trips].sort((a, b) => Number(b.favorite) - Number(a.favorite) || b.updated_at - a.updated_at).slice(0, 12)

  const sidebar = (
    <nav className="flex h-full flex-col bg-sidebar" aria-label="Main">
      <Link to="/" className="flex items-center gap-2 px-4 pt-4 pb-3">
        <img src="/favicon.svg" alt="" className="size-7" />
        <span className="font-serif text-xl font-semibold tracking-tight">TravelGenie</span>
      </Link>
      <div className="px-3">
        <button type="button" onClick={() => navigate('/new')}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2.5 text-sm font-medium text-accent-ink transition hover:opacity-90">
          <Plus className="size-4" /> Plan a new trip
        </button>
        <div className="space-y-0.5">
          <NavItem to="/" icon={LayoutDashboard} end>Dashboard</NavItem>
          <NavItem to="/knowledge" icon={Database}>Knowledge base</NavItem>
          <NavItem to="/settings" icon={SettingsIcon}>Settings</NavItem>
          {canInstall && (
            <button type="button" onClick={install}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-accent hover:bg-surface-2">
              <Download className="size-4" /> Install app
            </button>
          )}
        </div>
      </div>

      <div className="mt-5 flex-1 overflow-y-auto px-3 pb-3">
        <div className="px-2.5 pb-1.5 text-[11px] font-semibold tracking-[0.12em] text-faint uppercase">Your trips</div>
        {loaded && recent.length === 0 && <p className="px-2.5 py-1 text-xs text-faint">No trips yet.</p>}
        {recent.map(t => (
          <NavLink key={t.id} to={`/trips/${t.id}`}
            className={({ isActive }) => `flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm ${isActive ? 'bg-surface-2 text-ink' : 'text-muted hover:bg-surface-2/70 hover:text-ink'}`}>
            {t.favorite ? <Star className="size-3.5 shrink-0 fill-accent text-accent" /> : <span className="size-1.5 shrink-0 rounded-full bg-faint" />}
            <span className="truncate">{t.title}</span>
          </NavLink>
        ))}
      </div>

      <div className="flex gap-3 px-5 pb-2 text-[11px] text-faint">
        <Link to="/privacy" className="hover:text-ink">Privacy</Link>
        <Link to="/terms" className="hover:text-ink">Terms</Link>
      </div>
      <div className="flex items-center gap-2.5 border-t border-line p-3">
        <Avatar name={user.name} url={user.avatar_url} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{user.name}</div>
          <div className="truncate text-xs text-faint">{user.email}</div>
        </div>
        <button type="button" onClick={async () => { await logout(); navigate('/login') }}
          aria-label="Log out" title="Log out" className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
          <LogOut className="size-4" />
        </button>
      </div>
    </nav>
  )

  return (
    <TripsContext.Provider value={{ trips, loaded, refresh }}>
      <div className="flex h-full overflow-hidden">
        <aside className="hidden w-64 shrink-0 border-r border-line md:block">{sidebar}</aside>
        {mobileOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setMobileOpen(false)} aria-hidden />
            <aside className="fixed inset-y-0 left-0 z-50 w-72 border-r border-line md:hidden">
              <button type="button" onClick={() => setMobileOpen(false)} aria-label="Close menu"
                className="absolute top-4 right-3 rounded-lg p-1.5 text-muted hover:bg-surface-2"><X className="size-4" /></button>
              {sidebar}
            </aside>
          </>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3 md:hidden">
            <button type="button" onClick={() => setMobileOpen(true)} aria-label="Open menu" className="rounded-lg p-1.5 text-muted hover:bg-surface-2">
              <Menu className="size-5" />
            </button>
            <img src="/favicon.svg" alt="" className="size-6" />
            <span className="font-serif text-lg font-semibold">TravelGenie</span>
          </div>
          {!online && (
            <div role="status" className="flex shrink-0 items-center justify-center gap-2 bg-warn/15 px-3 py-1.5 text-xs text-ink">
              <WifiOff className="size-3.5 text-warn" /> You're offline: showing your saved trips. Planning and chat need internet.
            </div>
          )}
          <main className="min-h-0 flex-1 overflow-hidden"><Outlet /></main>
        </div>
      </div>
    </TripsContext.Provider>
  )
}
