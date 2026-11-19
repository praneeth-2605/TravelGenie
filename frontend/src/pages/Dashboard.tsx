import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, CalendarDays, Compass, Globe2, Loader2, Plus, Star, Trash2 } from 'lucide-react'
import { api, money, TIER_META, uid, type TripSummary } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useTrips } from '../components/AppShell'

const GRADIENTS = [
  'from-[#1f4e46] to-[#c8603f]', 'from-[#2a3d66] to-[#d98f5c]', 'from-[#5b3a5e] to-[#e0a24f]',
  'from-[#23585e] to-[#8fb996]', 'from-[#6b3b2a] to-[#e3b26b]', 'from-[#2f3e4e] to-[#7fa7c9]',
]
function gradientFor(text: string) {
  let h = 0
  for (const c of text) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return GRADIENTS[h % GRADIENTS.length]
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function daysUntil(dateStr: string | null) {
  if (!dateStr) return null
  const d = new Date(`${dateStr}T00:00:00`)
  return Math.ceil((d.getTime() - Date.now()) / 86_400_000)
}

function TripCard({ t, onChange }: { t: TripSummary; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const until = daysUntil(t.start_date)
  const place = t.destination ?? t.title

  const fav = async (e: React.MouseEvent) => {
    e.preventDefault()
    await api.patchTrip(t.id, { favorite: !t.favorite })
    onChange()
  }
  const remove = async (e: React.MouseEvent) => {
    e.preventDefault()
    if (!confirm(`Delete "${t.title}"? This can't be undone.`)) return
    setBusy(true)
    await api.deleteTrip(t.id)
    onChange()
  }

  return (
    <Link to={`/trips/${t.id}`} className={`group overflow-hidden rounded-2xl border border-line bg-surface transition hover:-translate-y-0.5 hover:shadow-[0_12px_30px_-16px_rgba(0,0,0,0.35)] ${busy ? 'opacity-50' : ''}`}>
      <div className={`relative h-28 bg-gradient-to-br ${gradientFor(place)} p-4 text-white`}>
        <div className="font-serif text-2xl font-semibold drop-shadow-sm">{place}</div>
        <div className="mt-0.5 text-sm text-white/80">
          {t.days ? `${t.days} days` : 'Draft'}{t.start_date ? ` · ${new Date(`${t.start_date}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
        </div>
        {until != null && until >= 0 && until < 400 && (
          <span className="absolute right-3 bottom-3 rounded-full bg-black/30 px-2 py-0.5 text-xs backdrop-blur">in {until} days</span>
        )}
        <div className="absolute top-2.5 right-2.5 flex gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
          <button type="button" onClick={fav} aria-label={t.favorite ? 'Unstar trip' : 'Star trip'} className="rounded-lg bg-black/25 p-1.5 backdrop-blur hover:bg-black/40">
            <Star className={`size-4 ${t.favorite ? 'fill-white' : ''}`} />
          </button>
          <button type="button" onClick={remove} aria-label="Delete trip" className="rounded-lg bg-black/25 p-1.5 backdrop-blur hover:bg-black/40">
            <Trash2 className="size-4" />
          </button>
        </div>
        {t.favorite && <Star className="absolute top-3 left-auto right-3 size-4 fill-white group-hover:hidden" />}
      </div>
      <div className="p-4">
        {t.options.length ? (
          <div className="grid grid-cols-3 gap-2">
            {t.options.map(o => (
              <div key={o.tier} className="rounded-lg bg-surface-2 px-2 py-1.5">
                <div className="truncate text-[11px] text-faint">{TIER_META[o.tier]?.emoji} {TIER_META[o.tier]?.label}</div>
                <div className="truncate text-sm font-semibold tabular-nums">{money(o.total, t.currency)}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No plan yet. Open to continue.</p>
        )}
        {t.summary && <p className="mt-3 line-clamp-2 text-sm text-muted">{t.summary}</p>}
      </div>
    </Link>
  )
}

export function Dashboard() {
  const { user } = useAuth()
  const { trips, loaded, refresh } = useTrips()
  const navigate = useNavigate()
  const [quick, setQuick] = useState('')

  const stats = useMemo(() => {
    const planned = trips.filter(t => t.options.length)
    const upcoming = trips
      .map(t => ({ t, d: daysUntil(t.start_date) }))
      .filter(x => x.d != null && x.d >= 0)
      .sort((a, b) => (a.d ?? 0) - (b.d ?? 0))[0]
    const destinations = new Set(trips.map(t => t.destination?.toLowerCase()).filter(Boolean))
    return { planned: planned.length, upcoming, destinations: destinations.size, days: planned.reduce((a, t) => a + (t.days ?? 0), 0) }
  }, [trips])

  const sorted = [...trips].sort((a, b) => Number(b.favorite) - Number(a.favorite) || b.updated_at - a.updated_at)

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted">{greeting()},</p>
            <h1 className="font-serif text-4xl font-semibold tracking-tight">{user?.name.split(' ')[0]}</h1>
          </div>
          <button type="button" onClick={() => navigate('/new')}
            className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-ink transition hover:opacity-90">
            <Plus className="size-4" /> Plan a new trip
          </button>
        </div>

        {/* Quick start */}
        <form onSubmit={e => { e.preventDefault(); if (quick.trim()) navigate(`/trips/${uid()}`, { state: { initialMessage: quick.trim() } }) }}
          className="mt-6 flex items-center gap-2 rounded-2xl border border-line bg-surface p-2 pl-4 shadow-[0_8px_30px_-18px_rgba(0,0,0,0.3)] focus-within:border-accent/60">
          <Compass className="size-5 shrink-0 text-accent" />
          <input value={quick} onChange={e => setQuick(e.target.value)} aria-label="Describe a trip"
            placeholder="Describe a trip… e.g. 5 days in Kyoto in April for 2, ₹1.5L budget, temples and food"
            className="min-w-0 flex-1 bg-transparent py-2 text-[15px] placeholder:text-faint focus:outline-none" />
          <button type="submit" disabled={!quick.trim()} aria-label="Start planning"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink disabled:opacity-30">
            <ArrowRight className="size-4" />
          </button>
        </form>

        {/* Stats */}
        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-2xl border border-line bg-surface p-4">
            <Compass className="size-5 text-accent" />
            <div className="mt-3 text-2xl font-semibold tabular-nums">{stats.planned}</div>
            <div className="text-xs text-muted">Trips planned</div>
          </div>
          <div className="rounded-2xl border border-line bg-surface p-4">
            <Globe2 className="size-5 text-accent" />
            <div className="mt-3 text-2xl font-semibold tabular-nums">{stats.destinations}</div>
            <div className="text-xs text-muted">Destinations</div>
          </div>
          <div className="rounded-2xl border border-line bg-surface p-4">
            <CalendarDays className="size-5 text-accent" />
            <div className="mt-3 text-2xl font-semibold tabular-nums">{stats.days}</div>
            <div className="text-xs text-muted">Days of travel planned</div>
          </div>
          <div className="rounded-2xl border border-line bg-surface p-4">
            <Star className="size-5 text-accent" />
            {stats.upcoming ? (
              <>
                <div className="mt-3 truncate text-2xl font-semibold">{stats.upcoming.t.destination}</div>
                <div className="text-xs text-muted">Next trip · in {stats.upcoming.d} days</div>
              </>
            ) : (
              <>
                <div className="mt-3 text-2xl font-semibold">—</div>
                <div className="text-xs text-muted">No upcoming trip</div>
              </>
            )}
          </div>
        </div>

        {/* Trips */}
        <h2 className="mt-10 mb-4 text-lg font-semibold">Your trips</h2>
        {!loaded ? (
          <Loader2 className="size-6 animate-spin text-faint" />
        ) : sorted.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-line p-10 text-center">
            <div className="text-4xl">🧭</div>
            <h3 className="mt-3 font-serif text-2xl font-semibold">Your first trip is one sentence away</h3>
            <p className="mx-auto mt-2 max-w-md text-muted">Tell TravelGenie where and for how long. You'll get a budget, a luxury and a your-budget plan with real stays and sights.</p>
            <button type="button" onClick={() => navigate('/new')} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-ink">
              <Plus className="size-4" /> Plan a trip
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {sorted.map(t => <TripCard key={t.id} t={t} onChange={refresh} />)}
          </div>
        )}
      </div>
    </div>
  )
}
