import type { ReactNode } from 'react'
import { ArrowRight, BedDouble, CalendarDays, Check, CloudSun, Globe, Loader2, Map as MapIcon, TrainFront } from 'lucide-react'
import { money, nightlyRange, stayLabel, TIER_META, type Tier, type TripPlan } from '../../lib/api'
import { MODE_ICON, priceRange } from './GettingThere'
import { weatherIcon } from './WeatherPanel'

export type SectionTab = 'overview' | 'yourplan' | 'options' | 'itinerary' | 'transport' | 'stays' | 'weather' | 'web' | 'map'

function SectionCard({ title, icon: Icon, onOpen, children, cta }: {
  title: string; icon: typeof CloudSun; onOpen: () => void; children: ReactNode; cta: string
}) {
  return (
    <section className="flex flex-col rounded-2xl border border-line bg-surface p-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-muted uppercase"><Icon className="size-4 text-accent" /> {title}</h3>
      <div className="mt-3 flex-1">{children}</div>
      <button type="button" onClick={onOpen} className="mt-4 inline-flex items-center gap-1 self-start text-sm font-medium text-accent hover:underline">
        {cta} <ArrowRight className="size-3.5" />
      </button>
    </section>
  )
}

export function Overview({ plan, onOpen, onChoose, choosing, selected }: {
  plan: TripPlan; onOpen: (t: SectionTab) => void; onChoose: (t: Tier) => void; choosing: Tier | null; selected: Tier | null
}) {
  const cur = plan.currency
  const t = plan.transport
  const modes = (t?.modes ?? []).filter(m => m.available).sort((a, b) => (a.price_min ?? Infinity) - (b.price_min ?? Infinity))

  return (
    <div className="space-y-6">
      {plan.answer && <div className="rounded-2xl border border-accent/30 bg-accent-soft/40 p-4 text-[15px] font-medium">{plan.answer}</div>}
      <p className="text-[15px] leading-relaxed">{plan.summary}</p>

      {/* The three options */}
      <section>
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">Pick your plan</h2>
          <button type="button" onClick={() => onOpen('options')} className="text-sm font-medium text-accent hover:underline">Compare in detail</button>
        </div>
        <div className="grid gap-3 @2xl:grid-cols-3">
          {plan.options.map(o => {
            const meta = TIER_META[o.tier]
            const isSel = selected === o.tier
            const GtIcon = o.getting_there ? MODE_ICON[o.getting_there.mode as keyof typeof MODE_ICON] : null
            return (
              <article key={o.tier} className={`flex flex-col rounded-2xl border bg-surface p-4 ${isSel ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'}`}>
                <div className="text-sm text-muted">{meta.emoji} {o.label}</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">{money(o.total, cur)}</div>
                <div className="text-xs text-muted">{money(o.per_person, cur)} per person</div>
                <div className="mt-3 space-y-1 text-sm">
                  <div className="flex items-center gap-1.5"><BedDouble className="size-3.5 shrink-0 text-faint" /><span className="truncate">{stayLabel(plan, o)}</span></div>
                  {o.getting_there && GtIcon && (
                    <div className="flex items-center gap-1.5"><GtIcon className="size-3.5 shrink-0 text-faint" /><span className="truncate capitalize">{o.getting_there.mode}{o.getting_there.duration ? ` · ${o.getting_there.duration}` : ''}</span></div>
                  )}
                </div>
                <button type="button" disabled={choosing != null} onClick={() => onChoose(o.tier)}
                  className={`mt-4 flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition disabled:opacity-60 ${isSel ? 'bg-accent text-accent-ink' : 'border border-accent/50 text-accent hover:bg-accent hover:text-accent-ink'}`}>
                  {choosing === o.tier ? <Loader2 className="size-4 animate-spin" /> : isSel ? <Check className="size-4" /> : null}
                  {isSel ? 'Your plan · open' : choosing === o.tier ? 'Building your plan…' : 'Choose this plan'}
                </button>
              </article>
            )
          })}
        </div>
      </section>

      {/* Sections */}
      <div className="grid gap-4 @xl:grid-cols-2 @4xl:grid-cols-3">
        <SectionCard title="Weather" icon={CloudSun} onOpen={() => onOpen('weather')} cta="Full weather">
          {plan.weather ? (
            <div className="grid grid-cols-5 gap-1">
              {plan.weather.daily.slice(0, 5).map(d => {
                const Icon = weatherIcon(d.condition)
                return (
                  <div key={d.date} className="rounded-lg bg-surface-2 py-1.5 text-center">
                    <div className="text-[10px] text-faint">{new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' })}</div>
                    <Icon className="mx-auto my-0.5 size-4 text-accent" />
                    <div className="text-xs font-semibold">{Math.round(d.max_c)}°</div>
                  </div>
                )
              })}
            </div>
          ) : <p className="text-xs text-faint">Seasonal outlook (trip is beyond the live forecast)</p>}
          {plan.weather_note && <p className="mt-2 line-clamp-4 text-sm text-muted">{plan.weather_note}</p>}
        </SectionCard>

        <SectionCard title="Getting there" icon={TrainFront} onOpen={() => onOpen('transport')} cta={t ? 'All ways to travel' : 'Add your starting city'}>
          {t && modes.length ? (
            <>
              <p className="mb-2 text-sm text-muted">From <strong className="text-ink">{t.origin}</strong>{t.distance_km ? ` · ~${t.distance_km.toLocaleString()} km` : ''}</p>
              <ul className="space-y-1.5">
                {modes.slice(0, 4).map((m, i) => {
                  const Icon = MODE_ICON[m.mode]
                  return (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <Icon className="size-4 shrink-0 text-accent" />
                      <span className="capitalize">{m.mode}{m.label ? ` (${m.label})` : ''}</span>
                      <span className="text-faint">{m.duration}</span>
                      <span className="ml-auto font-medium tabular-nums">{priceRange(m, t.currency)}</span>
                    </li>
                  )
                })}
              </ul>
            </>
          ) : <p className="text-sm text-muted">Tell me where you're starting from to compare flights, trains, buses and driving.</p>}
        </SectionCard>

        <SectionCard title="Hotels & hostels" icon={BedDouble} onOpen={() => onOpen('stays')} cta="Choose your hotel">
          <ul className="space-y-2">
            {plan.options.map(o => (
              <li key={o.tier} className="text-sm">
                <div className="text-xs text-faint">{TIER_META[o.tier].emoji} {o.label} · {o.stay.candidates.length} to choose from</div>
                <div className="flex items-baseline gap-2"><span className="truncate font-medium">{stayLabel(plan, o)}</span>
                  {nightlyRange(o, cur) ? <span className="ml-auto shrink-0 text-xs text-muted tabular-nums">{nightlyRange(o, cur)}</span> : null}</div>
              </li>
            ))}
          </ul>
        </SectionCard>

        <SectionCard title="Itinerary" icon={CalendarDays} onOpen={() => onOpen('itinerary')} cta="Day-by-day plan">
          <ol className="space-y-1.5">
            {plan.days.map(d => (
              <li key={d.day} className="flex gap-2 text-sm">
                <span className="grid size-5 shrink-0 place-items-center rounded-md bg-accent-soft text-[11px] font-semibold text-accent">{d.day}</span>
                <span className="truncate">{d.title}</span>
              </li>
            ))}
          </ol>
        </SectionCard>

        <SectionCard title="Web search" icon={Globe} onOpen={() => onOpen('web')} cta="All results & sources">
          {plan.web_results?.length ? (
            <ul className="space-y-2">
              {plan.web_results.slice(0, 3).map((r, i) => (
                <li key={i} className="text-sm">
                  <div className="font-medium">{r.title}</div>
                  <p className="line-clamp-2 text-xs text-muted">{r.snippet}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No web results yet.</p>}
        </SectionCard>

        <SectionCard title="Map" icon={MapIcon} onOpen={() => onOpen('map')} cta="Open map">
          <p className="text-sm text-muted">
            {plan.markers.filter(m => m.kind !== 'stay').length} sights and {plan.markers.filter(m => m.kind === 'stay').length} stays pinned,
            coloured by day.
          </p>
        </SectionCard>
      </div>
    </div>
  )
}
