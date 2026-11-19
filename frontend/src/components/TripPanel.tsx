import { useEffect, useRef } from 'react'
import { BookOpen, Cloud, CloudRain, CloudSun, FileText, Globe, Sun, Ticket, X } from 'lucide-react'
import type { Source, Trip, Weather } from '../lib/api'

interface Props {
  trip?: Trip
  weather?: Weather | null
  bookings?: string[]
  sources: Source[]
  activeSource: number | null
  onClose: () => void
}

function weatherIcon(condition: string) {
  const c = condition.toLowerCase()
  if (c.includes('rain') || c.includes('drizzle') || c.includes('thunder')) return CloudRain
  if (c.includes('cloud')) return Cloud
  if (c.includes('clear')) return Sun
  return CloudSun
}

const SOURCE_ICON = { guide: BookOpen, upload: FileText, web: Globe } as Record<string, typeof Globe>

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-line px-5 py-4">
      <h3 className="mb-3 text-xs font-semibold tracking-[0.14em] text-faint uppercase">{title}</h3>
      {children}
    </section>
  )
}

export function TripPanel({ trip, weather, bookings, sources, activeSource, onClose }: Props) {
  const refs = useRef(new Map<number, HTMLLIElement>())

  useEffect(() => {
    if (activeSource != null) refs.current.get(activeSource)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeSource])

  const facts: [string, string][] = []
  if (trip) {
    if (trip.days) facts.push(['Length', `${trip.days} days`])
    if (trip.start_date) facts.push(['Starts', trip.start_date])
    if (trip.travelers) facts.push(['Travellers', String(trip.travelers)])
    if (trip.budget) facts.push(['Budget', `${trip.budget.toLocaleString()} ${trip.currency ?? ''}`.trim()])
    if (trip.style) facts.push(['Style', trip.style])
    if (trip.origin) facts.push(['From', trip.origin])
  }

  return (
    <aside className="flex h-full w-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          <div className="text-xs text-faint">Trip</div>
          <div className="truncate font-serif text-lg font-semibold">
            {trip?.destination ? `${trip.destination}${trip.country ? `, ${trip.country}` : ''}` : 'No destination yet'}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close trip panel" className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {(facts.length > 0 || !!trip?.interests?.length) && (
          <Section title="Brief">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
              {facts.map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-faint">{k}</dt>
                  <dd className="font-medium capitalize">{v}</dd>
                </div>
              ))}
            </dl>
            {!!trip?.interests?.length && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {trip.interests.map(i => (
                  <span key={i} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs text-accent">{i}</span>
                ))}
              </div>
            )}
          </Section>
        )}

        {weather && (
          <Section title={`Forecast · ${weather.location}`}>
            <div className="grid grid-cols-5 gap-1.5">
              {weather.daily.slice(0, 5).map(d => {
                const Icon = weatherIcon(d.condition)
                const day = new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' })
                return (
                  <div key={d.date} className="rounded-lg bg-surface-2 px-1 py-2 text-center" title={`${d.condition}, ${d.rain_mm}mm rain`}>
                    <div className="text-[11px] text-faint">{day}</div>
                    <Icon className="mx-auto my-1 size-5 text-accent" />
                    <div className="text-xs font-medium">{Math.round(d.max_c)}°</div>
                    <div className="text-[11px] text-faint">{Math.round(d.min_c)}°</div>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-[11px] text-faint">Fetched {weather.fetched_at}</p>
          </Section>
        )}

        {!!bookings?.length && (
          <Section title="Simulated bookings">
            <ul className="space-y-2">
              {bookings.map(b => (
                <li key={b} className="flex gap-2 text-sm">
                  <Ticket className="mt-0.5 size-4 shrink-0 text-accent" />
                  <span>{b.replace(/^\[SIMULATED\]\s*/, '')}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-faint">Not real reservations. Nothing has been booked or charged.</p>
          </Section>
        )}

        <Section title={`Sources${sources.length ? ` · ${sources.length}` : ''}`}>
          {sources.length === 0 ? (
            <p className="text-sm text-muted">Sources the agents used will appear here, linked to the citations in each answer.</p>
          ) : (
            <ol className="space-y-2">
              {sources.map(s => {
                const Icon = SOURCE_ICON[s.source_type] ?? FileText
                const active = s.n === activeSource
                const isUrl = s.source.startsWith('http')
                return (
                  <li
                    key={s.n}
                    ref={el => { if (el) refs.current.set(s.n, el); else refs.current.delete(s.n) }}
                    className={`rounded-xl border p-3 text-sm transition ${active ? 'border-accent bg-accent-soft/50' : 'border-line'}`}
                  >
                    <div className="flex items-start gap-2">
                      <span className="grid size-5 shrink-0 place-items-center rounded-md bg-accent-soft font-mono text-[11px] text-accent">{s.n}</span>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium leading-snug">
                          {isUrl ? <a href={s.source} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">{s.title}</a> : s.title}
                        </div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-faint">
                          <Icon className="size-3" />
                          <span className="capitalize">{s.source_type}</span>
                          {s.section && <span className="truncate">· {s.section.split(' > ').slice(-1)[0]}</span>}
                          {s.page && <span>· p.{s.page}</span>}
                          <span className="ml-auto font-mono" title="Cross-encoder relevance score">{s.score.toFixed(1)}</span>
                        </div>
                      </div>
                    </div>
                    <p className={`mt-2 text-xs leading-relaxed text-muted ${active ? '' : 'line-clamp-3'}`}>{s.text.replace(/\*\*|__|^#+\s*/gm, '')}</p>
                  </li>
                )
              })}
            </ol>
          )}
        </Section>
      </div>
    </aside>
  )
}
