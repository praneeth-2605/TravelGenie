import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  BedDouble, CalendarDays, CloudSun, Globe, LayoutDashboard, LayoutGrid, Loader2, Map as MapIcon, MessageSquare, Sparkles, Star, TrainFront,
} from 'lucide-react'
import {
  ApiError, api, streamChat, uid, TIER_META, type AgentEvent, type ChatMessage, type Source, type Tier, type TripPlan,
} from '../lib/api'
import { useTrips } from '../components/AppShell'
import { META, StatusIcon, latest } from '../components/AgentTrace'
import { Composer } from '../components/Composer'
import { Message } from '../components/Message'
import { Options } from '../components/plan/Options'
import { Timeline } from '../components/plan/Timeline'
// Leaflet is large: load the map only when the Map tab opens.
const TripMap = lazy(() => import('../components/plan/TripMap').then(m => ({ default: m.TripMap })))
import { Stays } from '../components/plan/Stays'
import { ExportMenu } from '../components/plan/ExportMenu'
import { ShareMenu } from '../components/plan/ShareMenu'
import { Overview, type SectionTab } from '../components/plan/Overview'
import { GettingThere } from '../components/plan/GettingThere'
import { WeatherPanel } from '../components/plan/WeatherPanel'
import { WebPanel } from '../components/plan/WebPanel'
import { YourPlan } from '../components/plan/YourPlan'

type Tab = SectionTab
const TABS: { id: Tab; label: string; icon: typeof MapIcon }[] = [
  { id: 'yourplan', label: 'Your plan', icon: Star },
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'options', label: 'Options', icon: LayoutGrid },
  { id: 'itinerary', label: 'Itinerary', icon: CalendarDays },
  { id: 'transport', label: 'Getting there', icon: TrainFront },
  { id: 'stays', label: 'Stays', icon: BedDouble },
  { id: 'weather', label: 'Weather', icon: CloudSun },
  { id: 'web', label: 'Web', icon: Globe },
  { id: 'map', label: 'Map', icon: MapIcon },
]

function AgentsAtWork({ steps }: { steps: AgentEvent[] }) {
  const rows = latest(steps)
  const order = ['supervisor', 'research', 'weather', 'stays', 'sights', 'transport', 'web', 'booking', 'planner', 'writer']
  rows.sort((a, b) => order.indexOf(a.agent) - order.indexOf(b.agent))
  return (
    <div className="mx-auto max-w-xl py-10">
      <div className="text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-accent text-accent-ink"><Sparkles className="size-7" /></div>
        <h2 className="mt-4 font-serif text-2xl font-semibold">Your travel team is on it</h2>
        <p className="mt-1 text-sm text-muted">Each agent has its own job. This usually takes 10–20 seconds.</p>
      </div>
      <ol className="mt-8 space-y-2">
        {rows.map(r => {
          const m = META[r.agent]
          if (!m) return null
          return (
            <li key={r.agent} className="rise flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3">
              <m.icon className="mt-0.5 size-5 shrink-0 text-accent" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{m.label} <span className="font-normal text-faint">· {m.job}</span></div>
                {r.detail && <div className="mt-0.5 text-sm text-muted">{r.detail}</div>}
              </div>
              <StatusIcon status={r.status} />
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function TripWorkspace() {
  const { tripId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { refresh } = useTrips()
  const initialMessage = (location.state as { initialMessage?: string } | null)?.initialMessage

  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState('New trip')
  const [shareToken, setShareToken] = useState<string | null>(null)
  const [usage, setUsage] = useState<{ remaining: number | null; limit: number } | null>(null)
  const refreshUsage = useCallback(() => { api.usage().then(setUsage).catch(() => {}) }, [])
  useEffect(() => { refreshUsage() }, [refreshUsage])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [plan, setPlan] = useState<TripPlan | null>(null)
  const [sources, setSources] = useState<Source[]>([])
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')
  const [choosing, setChoosing] = useState<Tier | null>(null)
  const [chooseError, setChooseError] = useState<string | null>(null)
  const [activeSource, setActiveSource] = useState<number | null>(null)
  const selected: Tier | null = plan?.selected_tier || null
  const [focusId, setFocusId] = useState<string | null>(null)
  const [mobilePane, setMobilePane] = useState<'chat' | 'plan'>('plan')

  const abortRef = useRef<AbortController | null>(null)
  const sentInitial = useRef(false)
  const tokenBuf = useRef('')
  const frame = useRef<number | null>(null)
  const scroller = useRef<HTMLDivElement>(null)

  const updateMsg = useCallback((id: string, fn: (m: ChatMessage) => ChatMessage) => {
    setMessages(ms => ms.map(m => (m.id === id ? fn(m) : m)))
  }, [])

  const send = useCallback(async (text: string) => {
    const assistantId = uid()
    setMessages(ms => [...ms, { id: uid(), role: 'user', content: text },
      { id: assistantId, role: 'assistant', content: '', steps: [], streaming: true }])
    setBusy(true)
    setMobilePane(p => (plan ? p : 'plan'))

    const flush = () => {
      frame.current = null
      const chunk = tokenBuf.current
      tokenBuf.current = ''
      if (chunk) updateMsg(assistantId, m => ({ ...m, content: m.content + chunk }))
    }
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await streamChat(tripId, text, {
        onAgent: e => updateMsg(assistantId, m => ({ ...m, steps: [...(m.steps ?? []), e] })),
        onToken: t => {
          tokenBuf.current += t
          if (frame.current == null) frame.current = requestAnimationFrame(flush)
        },
        onFinal: f => {
          if (frame.current != null) cancelAnimationFrame(frame.current)
          tokenBuf.current = ''
          updateMsg(assistantId, m => ({ ...m, content: f.answer, sources: f.sources, hasPlan: !!f.plan, streaming: false }))
          setSources(f.sources)
          if (f.plan) {
            setPlan(f.plan)
            setTab(f.plan.selected_tier ? 'yourplan' : 'overview')
            setMobilePane('plan')
            if (f.trip.destination) setTitle(`${f.trip.destination} · ${f.trip.days ?? f.plan.days.length} days`)
          }
          refresh()
        },
        onError: msg => updateMsg(assistantId, m => ({ ...m, error: msg, streaming: false })),
      }, ctrl.signal)
    } catch (err) {
      const aborted = (err as Error).name === 'AbortError'
      updateMsg(assistantId, m => ({ ...m, streaming: false, error: aborted ? undefined : (err as Error).message,
        content: m.content + tokenBuf.current + (aborted ? '\n\n_Stopped._' : '') }))
      tokenBuf.current = ''
    } finally {
      updateMsg(assistantId, m => (m.streaming ? { ...m, streaming: false } : m))
      setBusy(false)
      refreshUsage()
      abortRef.current = null
    }
  }, [tripId, plan, updateMsg, refresh, refreshUsage])

  // Load the trip (or start a new one with the message from the form).
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setPlan(null)
    setMessages([])
    sentInitial.current = false
    api.trip(tripId).then(t => {
      if (cancelled) return
      setTitle(t.title)
      setShareToken(t.share_token ?? null)
      setPlan(t.plan)
      setTab(t.plan?.selected_tier ? 'yourplan' : 'overview')
      setSources(t.sources)
      setMessages(t.messages.map((m, i) => ({ id: `h${i}`, role: m.role, content: m.content,
        hasPlan: m.role === 'assistant' && !!t.plan && i === t.messages.length - 1 })))
    }).catch(err => {
      if (cancelled) return
      if (!(err instanceof ApiError && err.status === 404)) console.error(err)
      if (!initialMessage) navigate('/new', { replace: true })
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; abortRef.current?.abort() }
  }, [tripId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!loading && initialMessage && !sentInitial.current && messages.length === 0) {
      sentInitial.current = true
      navigate(location.pathname, { replace: true, state: null })  // don't resend on reload
      send(initialMessage)
    }
  }, [loading, initialMessage, messages.length, send, navigate, location.pathname])

  useEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  const choose = async (tier: Tier) => {
    // Already chosen with details: just open it.
    const opt = plan?.options.find(o => o.tier === tier)
    if (plan?.selected_tier === tier && opt?.details) { setTab('yourplan'); setMobilePane('plan'); return }
    setChoosing(tier)
    setChooseError(null)
    try {
      const res = await api.selectOption(tripId, tier)
      setPlan(res.plan)
      setTab('yourplan')
      setMessages(ms => [...ms,
        { id: uid(), role: 'user', content: `I choose the ${TIER_META[tier].label} option.` },
        { id: uid(), role: 'assistant', content: res.message }])
      refresh()
    } catch (err) {
      setChooseError((err as Error).message)
    } finally {
      setChoosing(null)
      refreshUsage()
    }
  }

  const cite = (n: number) => { setActiveSource(n); setTab('web'); setMobilePane('plan') }
  const showOnMap = (id: string) => { setFocusId(id); setTab('map') }
  const liveSteps = [...messages].reverse().find(m => m.role === 'assistant' && m.streaming)?.steps ?? []
  const planning = busy && !plan && liveSteps.length > 0

  if (loading) return <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-faint" /></div>

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-2.5">
        <h1 className="min-w-0 flex-1 truncate font-serif text-lg font-semibold">{title}</h1>
        <div className="flex rounded-lg border border-line p-0.5 lg:hidden">
          {(['chat', 'plan'] as const).map(p => (
            <button key={p} type="button" onClick={() => setMobilePane(p)}
              className={`rounded-md px-3 py-1 text-sm capitalize ${mobilePane === p ? 'bg-surface-2 font-medium' : 'text-muted'}`}>
              {p === 'chat' ? <MessageSquare className="inline size-4" /> : <LayoutGrid className="inline size-4" />} {p}
            </button>
          ))}
        </div>
        {plan && <ShareMenu tripId={tripId} title={title} initialToken={shareToken} />}
        {plan && <ExportMenu tripId={tripId} selected={selected ?? 'yours'} />}
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Chat */}
        <section className={`${mobilePane === 'chat' ? 'flex' : 'hidden'} w-full flex-col border-r border-line lg:flex lg:w-[380px] lg:shrink-0 xl:w-[420px]`}
          aria-label="Conversation">
          <div ref={scroller} className="flex-1 space-y-6 overflow-y-auto px-4 py-5">
            {messages.length === 0 && (
              <p className="pt-10 text-center text-sm text-muted">Describe your trip to get started.</p>
            )}
            {messages.map(m => (
              <Message key={m.id} message={m} onCite={cite} onOpenPlan={() => { setTab(selected ? 'yourplan' : 'overview'); setMobilePane('plan') }} />
            ))}
          </div>
          <div className="border-t border-line p-3">
            {selected && (
              <div className="mb-2 flex items-center gap-1.5 text-xs text-muted">
                <Star className="size-3.5 fill-accent text-accent" /> Chatting about your <strong className="text-ink">{TIER_META[selected].planName}</strong>
              </div>
            )}
            {usage?.remaining != null && (
              <div className={`mb-1.5 text-right text-[11px] ${usage.remaining <= 5 ? 'text-warn' : 'text-faint'}`}>
                {usage.remaining} of {usage.limit} AI requests left today
              </div>
            )}
            <Composer busy={busy} onSend={send} onStop={() => abortRef.current?.abort()}
              placeholder={selected ? `Ask about your ${TIER_META[selected].planName}…` : plan ? 'Refine it, e.g. “make it cheaper”' : 'Where to? From, days, budget…'} />
          </div>
        </section>

        {/* Plan */}
        <section className={`${mobilePane === 'plan' ? 'flex' : 'hidden'} min-w-0 flex-1 flex-col lg:flex`} aria-label="Trip plan">
          {plan ? (
            <>
              <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 pt-2" role="tablist">
                {TABS.filter(t => t.id !== 'yourplan' || selected).map(t => (
                  <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                    className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition ${tab === t.id ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:text-ink'} ${t.id === 'yourplan' ? 'text-accent' : ''}`}>
                    <t.icon className={`size-4 ${t.id === 'yourplan' ? 'fill-accent text-accent' : ''}`} /> {t.label}
                  </button>
                ))}
                {busy && <span className="ml-auto flex items-center gap-1.5 self-center pr-2 text-xs text-muted"><Loader2 className="size-3.5 animate-spin" /> Updating…</span>}
              </nav>
              {chooseError && (
                <div role="alert" className="mx-4 mt-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{chooseError}</div>
              )}
              <div key={tab} className={`@container min-h-0 flex-1 ${tab === 'map' ? 'p-4' : 'overflow-y-auto p-4 sm:p-6'}`}>
                {tab === 'yourplan' && selected && (
                  <YourPlan plan={plan} tier={selected} choosing={choosing === selected}
                    onRebuild={() => choose(selected)} onAsk={q => { setMobilePane('chat'); send(q) }}
                    onSwitch={() => setTab('options')} />
                )}
                {tab === 'overview' && <Overview plan={plan} onOpen={setTab} onChoose={choose} choosing={choosing} selected={selected} />}
                {tab === 'options' && <Options plan={plan} selected={selected} choosing={choosing} onChoose={choose} />}
                {tab === 'itinerary' && <Timeline plan={plan} onCite={cite} onShowOnMap={showOnMap} />}
                {tab === 'transport' && <GettingThere plan={plan} />}
                {tab === 'weather' && <WeatherPanel plan={plan} />}
                {tab === 'web' && <WebPanel plan={plan} sources={plan.sources.length ? plan.sources : sources} active={activeSource} />}
                {tab === 'map' && (
                  <Suspense fallback={<div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-faint" /></div>}>
                    <TripMap plan={plan} selected={selected ?? 'yours'} focusId={focusId} />
                  </Suspense>
                )}
                {tab === 'stays' && <Stays plan={plan} selected={selected ?? 'yours'} />}
              </div>
            </>
          ) : planning ? (
            <div className="overflow-y-auto px-4"><AgentsAtWork steps={liveSteps} /></div>
          ) : (
            <div className="grid flex-1 place-items-center p-8 text-center">
              <div className="max-w-sm">
                <LayoutGrid className="mx-auto size-8 text-faint" />
                <p className="mt-3 text-muted">Your three options (💰 Budget, 💎 Luxury, 🎯 Your budget) will appear here once you describe a trip with a destination and length.</p>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
