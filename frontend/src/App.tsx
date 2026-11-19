import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Map, PanelLeft } from 'lucide-react'
import { api, streamChat, type Health } from './lib/api'
import { loadThreads, saveThreads, titleFrom, uid, type ChatMessage, type Thread } from './lib/threads'
import { Composer } from './components/Composer'
import { EmptyState } from './components/EmptyState'
import { KnowledgeBase } from './components/KnowledgeBase'
import { Message } from './components/Message'
import { Sidebar } from './components/Sidebar'
import { TripPanel } from './components/TripPanel'

type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem('travelgenie.theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* ignore */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const isWide = () => window.matchMedia('(min-width: 1024px)').matches

export default function App() {
  const [threads, setThreads] = useState<Thread[]>(loadThreads)
  const [activeId, setActiveId] = useState<string | null>(() => threads[0]?.id ?? null)
  const [view, setView] = useState<'chat' | 'knowledge'>('chat')
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia('(min-width: 768px)').matches)
  const [panelOpen, setPanelOpen] = useState(false)
  const [activeSource, setActiveSource] = useState<number | null>(null)
  const [panelMsgId, setPanelMsgId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const tokenBuf = useRef('')
  const frame = useRef<number | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const pinnedToBottom = useRef(true)

  const thread = threads.find(t => t.id === activeId) ?? null

  useEffect(() => { saveThreads(threads) }, [threads])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('travelgenie.theme', theme) } catch { /* ignore */ }
  }, [theme])
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true))
  }, [])

  // Keep the view pinned to the bottom while streaming, unless the user scrolled up.
  useEffect(() => {
    const el = scroller.current
    if (el && pinnedToBottom.current) el.scrollTop = el.scrollHeight
  }, [thread?.messages])

  const updateThread = useCallback((id: string, fn: (t: Thread) => Thread) => {
    setThreads(ts => ts.map(t => (t.id === id ? fn(t) : t)))
  }, [])

  const updateMessage = useCallback((tid: string, mid: string, fn: (m: ChatMessage) => ChatMessage) => {
    updateThread(tid, t => ({ ...t, messages: t.messages.map(m => (m.id === mid ? fn(m) : m)) }))
  }, [updateThread])

  const send = async (text: string) => {
    let tid = activeId
    if (!tid || !thread) {
      tid = uid()
      const fresh: Thread = { id: tid, title: titleFrom(text), updatedAt: Date.now(), messages: [] }
      setThreads(ts => [fresh, ...ts])
      setActiveId(tid)
    }
    const threadId = tid
    const assistantId = uid()
    setThreads(ts => ts.map(t => t.id !== threadId ? t : {
      ...t,
      updatedAt: Date.now(),
      messages: [
        ...t.messages,
        { id: uid(), role: 'user', content: text },
        { id: assistantId, role: 'assistant', content: '', steps: [], streaming: true },
      ],
    }))
    setView('chat')
    setBusy(true)
    pinnedToBottom.current = true

    const flush = () => {
      frame.current = null
      const chunk = tokenBuf.current
      tokenBuf.current = ''
      if (chunk) updateMessage(threadId, assistantId, m => ({ ...m, content: m.content + chunk }))
    }

    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await streamChat(threadId, text, {
        onAgent: e => {
          updateMessage(threadId, assistantId, m => ({ ...m, steps: [...(m.steps ?? []), e] }))
          if (e.agent === 'supervisor' && e.status === 'done' && e.trip) {
            updateThread(threadId, t => ({ ...t, trip: e.trip }))
          }
        },
        onToken: tok => {
          tokenBuf.current += tok
          if (frame.current == null) frame.current = requestAnimationFrame(flush)
        },
        onFinal: f => {
          if (frame.current != null) cancelAnimationFrame(frame.current)
          tokenBuf.current = ''
          updateMessage(threadId, assistantId, m => ({ ...m, content: f.answer, sources: f.sources, streaming: false }))
          updateThread(threadId, t => ({ ...t, trip: f.trip, bookings: f.bookings, weather: f.weather ?? t.weather }))
          setPanelMsgId(assistantId)
          if (f.intent !== 'chat' && (f.sources.length || f.weather) && isWide()) setPanelOpen(true)
        },
        onError: msg => updateMessage(threadId, assistantId, m => ({ ...m, error: msg, streaming: false })),
      }, ctrl.signal)
    } catch (err) {
      const aborted = (err as Error).name === 'AbortError'
      updateMessage(threadId, assistantId, m => ({
        ...m,
        streaming: false,
        error: aborted ? undefined : (err as Error).message,
        content: m.content + tokenBuf.current + (aborted ? '\n\n_Stopped._' : ''),
      }))
      tokenBuf.current = ''
    } finally {
      updateMessage(threadId, assistantId, m => (m.streaming ? { ...m, streaming: false } : m))
      setBusy(false)
      abortRef.current = null
    }
  }

  const newTrip = () => {
    abortRef.current?.abort()
    setActiveId(null)
    setView('chat')
    setPanelOpen(false)
    setPanelMsgId(null)
    if (!isWide()) setSidebarOpen(false)
  }

  const selectThread = (id: string) => {
    setActiveId(id)
    setView('chat')
    setPanelMsgId(null)
    setActiveSource(null)
    if (!window.matchMedia('(min-width: 768px)').matches) setSidebarOpen(false)
  }

  const deleteThread = (id: string) => {
    setThreads(ts => ts.filter(t => t.id !== id))
    if (id === activeId) setActiveId(null)
  }

  const cite = (msgId: string, n: number) => {
    setPanelMsgId(msgId)
    setActiveSource(n)
    setPanelOpen(true)
  }

  const panelSources = useMemo(() => {
    const msgs = thread?.messages ?? []
    const msg = msgs.find(m => m.id === panelMsgId) ?? [...msgs].reverse().find(m => m.role === 'assistant' && m.sources?.length)
    return msg?.sources ?? []
  }, [thread, panelMsgId])

  const noKey = !!health?.missing_keys.includes('GROQ_API_KEY')
  const otherMissing = health?.missing_keys.filter(k => k !== 'GROQ_API_KEY') ?? []

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar */}
      {sidebarOpen && (
        <>
          <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setSidebarOpen(false)} aria-hidden />
          <div className="fixed inset-y-0 left-0 z-40 w-72 border-r border-line md:static md:w-64 md:shrink-0">
            <Sidebar
              threads={threads} activeId={activeId} view={view} theme={theme}
              onNew={newTrip} onSelect={selectThread} onDelete={deleteThread}
              onKnowledge={() => { setView('knowledge'); if (!window.matchMedia('(min-width: 768px)').matches) setSidebarOpen(false) }}
              onToggleTheme={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}
              onCollapse={() => setSidebarOpen(false)}
            />
          </div>
        </>
      )}

      {/* Main */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 px-3">
          {!sidebarOpen && (
            <button type="button" onClick={() => setSidebarOpen(true)} aria-label="Show sidebar" className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
              <PanelLeft className="size-4" />
            </button>
          )}
          <div className="min-w-0 flex-1 truncate text-sm text-muted">
            {view === 'knowledge' ? 'Knowledge base' : thread?.title ?? ''}
          </div>
          {view === 'chat' && thread && !panelOpen && (
            <button type="button" onClick={() => setPanelOpen(true)}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-ink">
              <Map className="size-4" /> Trip
            </button>
          )}
        </header>

        {(noKey || healthError) && (
          <div className="mx-auto mb-2 flex w-[calc(100%-2rem)] max-w-3xl items-start gap-2 rounded-xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />
            <span>
              {healthError
                ? 'Can’t reach the TravelGenie API. Start it with: uvicorn backend.api.main:app --port 8000'
                : <>Add <code className="font-mono">GROQ_API_KEY</code> to your <code className="font-mono">.env</code> and restart the API to start planning. The knowledge base works without it.</>}
            </span>
          </div>
        )}
        {!noKey && otherMissing.length > 0 && (
          <div className="mx-auto mb-2 w-full max-w-3xl px-4 text-xs text-faint">
            Running without {otherMissing.join(' and ')}: {otherMissing.includes('TAVILY_API_KEY') ? 'no web fallback' : ''}
            {otherMissing.length > 1 ? ', ' : ''}{otherMissing.includes('OPENWEATHERMAP_API_KEY') ? 'no live forecast' : ''}.
          </div>
        )}

        {view === 'knowledge' ? (
          <KnowledgeBase />
        ) : (
          <>
            <div
              ref={scroller}
              onScroll={e => {
                const el = e.currentTarget
                pinnedToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
              }}
              className="flex-1 overflow-y-auto"
            >
              {!thread || thread.messages.length === 0 ? (
                <EmptyState onPick={text => { if (!noKey && !busy) send(text) }} />
              ) : (
                <div className="mx-auto w-full max-w-3xl space-y-8 px-4 pt-4 pb-10">
                  {thread.messages.map(m => (
                    <Message key={m.id} message={m} onCite={n => cite(m.id, n)} />
                  ))}
                </div>
              )}
            </div>
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">
              <Composer busy={busy} disabled={noKey} onSend={send} onStop={() => abortRef.current?.abort()} autoFocus />
              <p className="mt-2 text-center text-[11px] text-faint">
                Plans are AI-generated. Check opening hours, prices and entry rules before you go. Bookings are simulated.
              </p>
            </div>
          </>
        )}
      </main>

      {/* Trip panel */}
      {panelOpen && view === 'chat' && thread && (
        <>
          <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setPanelOpen(false)} aria-hidden />
          <div className="fixed inset-y-0 right-0 z-40 w-[min(380px,100vw)] border-l border-line lg:static lg:z-auto lg:shrink-0">
            <TripPanel
              trip={thread.trip} weather={thread.weather} bookings={thread.bookings}
              sources={panelSources} activeSource={activeSource}
              onClose={() => { setPanelOpen(false); setActiveSource(null) }}
            />
          </div>
        </>
      )}
    </div>
  )
}
