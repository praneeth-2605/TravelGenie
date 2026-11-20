import { useState } from 'react'
import {
  AlertTriangle, BedDouble, Check, ChevronDown, CloudSun, Compass, Globe, Landmark, Loader2, MinusCircle, PenLine, Route, Search, Ticket,
  TrainFront,
} from 'lucide-react'
import type { AgentEvent, AgentName } from '../lib/api'

export const META: Record<AgentName, { label: string; icon: typeof Search; job: string }> = {
  supervisor: { label: 'Supervisor', icon: Compass, job: 'Understands your request and assigns agents' },
  research: { label: 'Research', icon: Search, job: 'Searches the knowledge base and the web' },
  weather: { label: 'Weather', icon: CloudSun, job: 'Checks the forecast or seasonal norms' },
  stays: { label: 'Stays', icon: BedDouble, job: 'Finds real hostels and hotels by price' },
  sights: { label: 'Sightseeing', icon: Landmark, job: 'Finds local sights and activities' },
  transport: { label: 'Transport', icon: TrainFront, job: 'Compares flights, trains, buses and driving' },
  web: { label: 'Web search', icon: Globe, job: 'Finds what to know before you go' },
  booking: { label: 'Booking', icon: Ticket, job: 'Makes simulated bookings' },
  planner: { label: 'Planner', icon: Route, job: 'Builds 3 budget options and your day plan' },
  writer: { label: 'Writer', icon: PenLine, job: 'Writes a cited answer' },
}

/** Collapse the event log into the latest state per agent, in first-seen order. */
export function latest(steps: AgentEvent[]) {
  const map = new Map<AgentName, AgentEvent>()
  for (const s of steps) map.set(s.agent, { ...map.get(s.agent), ...s, detail: s.detail || map.get(s.agent)?.detail || '' })
  return [...map.values()]
}

export function StatusIcon({ status }: { status: AgentEvent['status'] }) {
  if (status === 'running') return <Loader2 className="size-3.5 animate-spin text-accent" />
  if (status === 'done') return <Check className="size-3.5 text-ok" />
  if (status === 'error') return <AlertTriangle className="size-3.5 text-warn" />
  return <MinusCircle className="size-3.5 text-faint" />
}

export function AgentTrace({ steps, live }: { steps: AgentEvent[]; live: boolean }) {
  const [open, setOpen] = useState(false)
  const rows = latest(steps)
  if (!rows.length) return null
  const running = rows.find(r => r.status === 'running')
  const specialists = rows.filter(r => !['supervisor', 'writer', 'planner'].includes(r.agent)).length
  const summary = live && running
    ? `${META[running.agent].label}: ${running.detail || 'working'}…`
    : `${specialists} agent${specialists === 1 ? '' : 's'} consulted`
  const expanded = open

  return (
    <div className="mb-3 rounded-xl border border-line bg-surface-2/60 text-sm">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted hover:text-ink"
      >
        {live && running ? <Loader2 className="size-4 animate-spin text-accent" /> : <Compass className="size-4" />}
        <span className="truncate">{summary}</span>
        <div className="ml-auto flex -space-x-1">
          {rows.filter(r => r.agent !== 'supervisor').map(r => {
            const Icon = META[r.agent].icon
            return (
              <span key={r.agent} className="grid size-5 place-items-center rounded-full border border-line bg-surface">
                <Icon className="size-3" />
              </span>
            )
          })}
        </div>
        <ChevronDown className={`size-4 shrink-0 transition ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <ol className="space-y-1.5 border-t border-line px-3 py-2.5">
          {rows.map(r => {
            const Icon = META[r.agent].icon
            return (
              <li key={r.agent} className="rise flex items-start gap-2.5">
                <Icon className="mt-0.5 size-4 shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <span className="font-medium">{META[r.agent].label}</span>
                  {r.detail && <span className="text-muted"> — {r.detail}</span>}
                  {r.agent === 'supervisor' && r.agents && r.status === 'done' && (
                    <div className="mt-0.5 text-xs text-faint">
                      intent <span className="font-mono">{r.intent}</span>
                      {r.agents.length ? <> · routing to {r.agents.join(', ')}</> : ' · no specialists needed'}
                    </div>
                  )}
                  {r.queries && r.queries.length > 1 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.queries.map(q => (
                        <span key={q} className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-[11px] text-muted">{q}</span>
                      ))}
                    </div>
                  )}
                </div>
                <StatusIcon status={r.status} />
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
