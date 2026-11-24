import { Suspense, lazy, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, BedDouble, CalendarDays, LayoutGrid, Loader2, Map as MapIcon, TrainFront } from 'lucide-react'
import { api, type TripPlan } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Options } from '../components/plan/Options'
import { Timeline } from '../components/plan/Timeline'
import { GettingThere } from '../components/plan/GettingThere'
import { Stays } from '../components/plan/Stays'

const TripMap = lazy(() => import('../components/plan/TripMap').then(m => ({ default: m.TripMap })))

type Tab = 'options' | 'itinerary' | 'transport' | 'stays' | 'map'
const TABS: { id: Tab; label: string; icon: typeof MapIcon }[] = [
  { id: 'options', label: 'Options', icon: LayoutGrid },
  { id: 'itinerary', label: 'Itinerary', icon: CalendarDays },
  { id: 'transport', label: 'Getting there', icon: TrainFront },
  { id: 'stays', label: 'Stays', icon: BedDouble },
  { id: 'map', label: 'Map', icon: MapIcon },
]

/** Read-only view of a trip someone shared. No login needed. */
export function SharedTrip() {
  const { token = '' } = useParams()
  const { user } = useAuth()
  const [data, setData] = useState<{ title: string; plan: TripPlan } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('options')
  const [focusId, setFocusId] = useState<string | null>(null)

  useEffect(() => {
    api.publicTrip(token).then(d => { setData(d); document.title = `${d.title} · TravelGenie` })
      .catch(e => setError((e as Error).message))
  }, [token])

  const header = (
    <header className="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6">
      <Link to="/" className="flex items-center gap-2">
        <img src="/favicon.svg" alt="" className="size-7" />
        <span className="font-serif text-lg font-semibold">TravelGenie</span>
      </Link>
      <Link to={user ? '/new' : '/signup'} className="flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink hover:opacity-90">
        Plan your own trip <ArrowRight className="size-4" />
      </Link>
    </header>
  )

  if (error) {
    return (
      <div className="flex h-full flex-col">{header}
        <div className="grid flex-1 place-items-center p-8 text-center">
          <div><div className="text-4xl">🧭</div><p className="mt-3 text-muted">{error}</p></div>
        </div>
      </div>
    )
  }
  if (!data) return <div className="flex h-full flex-col">{header}<div className="grid flex-1 place-items-center"><Loader2 className="size-6 animate-spin text-faint" /></div></div>

  const { plan } = data
  return (
    <div className="flex h-full flex-col">
      {header}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mx-auto w-full max-w-6xl px-4 pt-6 sm:px-6">
          <p className="text-xs font-semibold tracking-[0.14em] text-accent uppercase">Shared trip plan</p>
          <h1 className="mt-1 font-serif text-3xl font-semibold tracking-tight">{data.title}</h1>
          <nav className="mt-5 flex gap-1 overflow-x-auto border-b border-line" role="tablist">
            {TABS.map(t => (
              <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm ${tab === t.id ? 'border-accent font-medium' : 'border-transparent text-muted hover:text-ink'}`}>
                <t.icon className="size-4" /> {t.label}
              </button>
            ))}
          </nav>
        </div>
        <div key={tab} className={`@container mx-auto w-full max-w-6xl min-h-0 flex-1 px-4 py-5 sm:px-6 ${tab === 'map' ? '' : 'overflow-y-auto'}`}>
          {tab === 'options' && <Options plan={plan} selected={plan.selected_tier} choosing={null} />}
          {tab === 'itinerary' && <Timeline plan={plan} onCite={() => {}} onShowOnMap={id => { setFocusId(id); setTab('map') }} />}
          {tab === 'transport' && <GettingThere plan={plan} />}
          {tab === 'stays' && <Stays plan={plan} selected={plan.selected_tier ?? 'yours'} />}
          {tab === 'map' && (
            <div className="h-[min(70vh,640px)]">
              <Suspense fallback={<div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-faint" /></div>}>
                <TripMap plan={plan} selected={plan.selected_tier ?? 'yours'} focusId={focusId} />
              </Suspense>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
