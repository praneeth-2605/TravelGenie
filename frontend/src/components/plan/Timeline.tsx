import { useState } from 'react'
import {
  Backpack, BedDouble, Clock, CloudSun, ExternalLink, Footprints, Landmark, Lightbulb, LogIn, LogOut, MapPin, PlaneLanding,
  PlaneTakeoff, Sparkles, Sun, TriangleAlert, Utensils, CarTaxiFront, TrainFront, Bus, Car, Ship,
} from 'lucide-react'
import { activeTier, pickedHotel, stayLabel, TIER_META, type Step, type Tier, type TripPlan } from '../../lib/api'
import { mapsDirections, mapsPlace } from '../../lib/links'
import { PlacePhoto } from './PlacePhoto'

export const DAY_COLORS = ['#c8603f', '#4f8f86', '#6c7fc2', '#d9a441', '#9b5fa8', '#3f7cb8', '#b8574f', '#5e9c4c', '#c47a2c', '#7a6a58']

const ICON: Record<Step['kind'], typeof Clock> = {
  arrive: PlaneLanding, depart: PlaneTakeoff, hotel: LogIn, start: BedDouble, end: LogOut,
  sight: Landmark, activity: Sparkles, meal: Utensils, free: Sun, travel: CarTaxiFront,
}

export const duration = (min?: number | null) => {
  if (!min) return ''
  const h = Math.floor(min / 60), m = min % 60
  return h ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`
}

/** Tier switcher used by the itinerary, stays and map. */
export function TierTabs({ plan, tier, onChange }: { plan: TripPlan; tier: Tier; onChange: (t: Tier) => void }) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1" role="tablist" aria-label="Option">
      {plan.options.map(o => (
        <button key={o.tier} type="button" role="tab" aria-selected={tier === o.tier} onClick={() => onChange(o.tier)}
          className={`rounded-lg px-3 py-1.5 text-sm transition ${tier === o.tier ? 'bg-accent font-medium text-accent-ink' : 'text-muted hover:text-ink'}`}>
          {TIER_META[o.tier].emoji} {o.label}{plan.selected_tier === o.tier ? ' ★' : ''}
        </button>
      ))}
    </div>
  )
}

function TravelRow({ s, from, color }: { s: Step; from: string | null; color: string }) {
  const walk = s.mode === 'walk'
  const Icon = walk ? Footprints : CarTaxiFront
  return (
    <li className="relative flex gap-3 pb-3">
      <span className="absolute top-0 bottom-0 left-[15px] w-px border-l border-dashed" style={{ borderColor: color }} aria-hidden />
      <span className="z-10 ml-[7px] grid size-[18px] shrink-0 place-items-center self-center rounded-full bg-surface">
        <Icon className="size-3.5 text-faint" />
      </span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5 pl-1.5 text-xs text-muted">
        <span className="w-11 shrink-0 tabular-nums text-faint">{s.time}</span>
        <span>{s.title.split(' to ')[0]}</span>
        <span className="font-medium text-ink tabular-nums">{s.distance_km} km · {duration(s.minutes)}</span>
        {s.estimated && <span className="text-faint" title="Straight-line estimate; road routing was unavailable">≈ estimate</span>}
        {from && !walk && (
          <a href={mapsDirections(from, s.title.replace(/^.*? to /, ''))} target="_blank" rel="noopener noreferrer"
            className="text-accent hover:underline">Directions</a>
        )}
      </div>
    </li>
  )
}

function StepRow({ s, color, destination, onCite, onShowOnMap, last }: {
  s: Step; color: string; destination: string; onCite: (n: number) => void; onShowOnMap: (id: string) => void; last: boolean
}) {
  const via = (s.kind === 'arrive' || s.kind === 'depart') ? /\bby (train|bus|car|ferry)\b/i.exec(s.detail ?? '')?.[1]?.toLowerCase() : undefined
  const Icon = via ? ({ train: TrainFront, bus: Bus, car: Car, ferry: Ship } as Record<string, typeof Clock>)[via] : ICON[s.kind] ?? Clock
  const visit = s.kind === 'sight' || s.kind === 'activity' || s.kind === 'meal'
  const p = s.place
  return (
    <li className="relative flex gap-3 pb-3">
      {!last && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-line" aria-hidden />}
      <span className="z-10 grid size-8 shrink-0 place-items-center rounded-full border bg-surface" style={{ borderColor: visit ? color : 'var(--line)' }}>
        <Icon className="size-4" style={{ color: visit ? color : 'var(--muted)' }} />
      </span>
      <div className={`min-w-0 flex-1 ${visit ? 'rounded-xl border border-line bg-surface p-2.5' : 'pt-1'}`}>
        <div className="flex gap-3">
          {visit && p && <PlacePhoto place={p} className="h-20 w-28 shrink-0 rounded-lg @xl:h-24 @xl:w-36" />}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-xs font-semibold tabular-nums" style={{ color }}>{s.time}{s.end && visit ? `–${s.end}` : ''}</span>
              <span className={visit ? 'font-semibold' : 'font-medium'}>{s.title}</span>
              {s.kind === 'free' && s.minutes ? <span className="text-xs text-faint">{duration(s.minutes)}</span> : null}
              {visit && s.minutes ? <span className="text-xs text-faint">{duration(s.minutes)}</span> : null}
              {s.unverified && (
                <span className="inline-flex items-center gap-0.5 rounded-full bg-warn/15 px-1.5 py-0.5 text-[10px] font-medium text-warn" title="Not found in Wikivoyage listings; check it exists before going">
                  <TriangleAlert className="size-3" /> not verified
                </span>
              )}
              {s.cite?.map(n => (
                <button key={n} type="button" onClick={() => onCite(n)}
                  className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-accent-soft px-1 font-mono text-[10px] text-accent hover:bg-accent hover:text-accent-ink">
                  {n}
                </button>
              ))}
            </div>
            {s.detail && <p className="mt-0.5 text-sm leading-relaxed text-muted">{s.detail}</p>}
            {visit && p && (
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-faint">
                {p.hours && <span className="flex items-center gap-1"><Clock className="size-3" />{p.hours}</span>}
                {p.price && <span>{p.price}</span>}
                {p.lat != null && (
                  <button type="button" onClick={() => onShowOnMap(p.id)} className="flex items-center gap-1 font-medium text-accent hover:underline">
                    <MapPin className="size-3" /> Map
                  </button>
                )}
                <a href={mapsPlace(p.name, p.area, destination)} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 font-medium text-accent hover:underline">
                  Google Maps <ExternalLink className="size-3" />
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    </li>
  )
}

export function Timeline({ plan, onCite, onShowOnMap, onOpenStays }: {
  plan: TripPlan
  onCite: (n: number) => void
  onShowOnMap: (placeId: string) => void
  onOpenStays?: () => void
}) {
  const [tier, setTier] = useState<Tier>(activeTier(plan))
  const days = plan.schedules?.[tier] ?? []
  const option = plan.options.find(o => o.tier === tier)
  const hotel = pickedHotel(plan, tier)
  const destination = plan.trip.destination ?? ''

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <TierTabs plan={plan} tier={tier} onChange={setTier} />
        {option && (
          <p className="text-sm text-muted">
            <BedDouble className="mr-1 inline size-4 text-accent" />
            {hotel ? <>Staying at <strong className="text-ink">{hotel.name}</strong></> : <>{stayLabel(plan, option)} · no hotel chosen yet</>}
            {onOpenStays && (
              <button type="button" onClick={onOpenStays} className="ml-2 font-medium text-accent hover:underline">
                {hotel ? 'Change' : 'Choose a hotel'}
              </button>
            )}
          </p>
        )}
      </div>

      {days.map(d => {
        const color = DAY_COLORS[(d.day - 1) % DAY_COLORS.length]
        const date = d.date ? new Date(`${d.date}T12:00:00`) : null
        const photos = d.steps.filter(s => s.place?.photo && s.kind !== 'hotel' && s.kind !== 'start' && s.kind !== 'end').slice(0, 4)
        let lastPlace: string | null = null
        return (
          <section key={d.day} className="overflow-hidden rounded-2xl border border-line bg-surface">
            {photos.length > 0 && (
              <div className={`grid h-32 gap-0.5 @xl:h-40`} style={{ gridTemplateColumns: `repeat(${photos.length}, minmax(0, 1fr))` }}>
                {photos.map(s => <PlacePhoto key={s.place!.id} place={s.place} size="url" className="size-full" />)}
              </div>
            )}
            <header className="flex items-center gap-3 border-b border-line px-4 py-3">
              <div className="grid size-11 shrink-0 place-items-center rounded-xl text-white" style={{ background: color }}>
                <div className="text-center leading-none">
                  <div className="text-[10px] font-medium tracking-wide uppercase opacity-80">Day</div>
                  <div className="text-lg font-semibold">{d.day}</div>
                </div>
              </div>
              <div className="min-w-0">
                <h3 className="truncate font-serif text-lg font-semibold">{d.title}</h3>
                <div className="text-xs text-muted">
                  {date && date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
                  {date && d.area ? ' · ' : ''}{d.area}
                  {d.steps.length > 0 && ` · ${d.steps[0].time}–${d.steps[d.steps.length - 1].time}`}
                </div>
              </div>
            </header>
            <ol className="px-4 pt-4 pb-1">
              {d.steps.map((s, i) => {
                if (s.kind === 'travel') return <TravelRow key={i} s={s} from={lastPlace} color={color} />
                if (s.place) lastPlace = [s.place.name, s.place.area, destination].filter(Boolean).join(', ')
                else if (s.kind === 'arrive') lastPlace = `${s.title.replace(/^Arrive at /, '')}, ${destination}`
                return <StepRow key={i} s={s} color={color} destination={destination} onCite={onCite} onShowOnMap={onShowOnMap}
                  last={i === d.steps.length - 1} />
              })}
            </ol>
          </section>
        )
      })}

      <p className="text-xs text-faint">
        Times use real road distances (OpenStreetMap routing) with a traffic allowance; arrival times are typical, so check your ticket.
        Photos © Wikimedia Commons contributors; “Area photo” shows the surroundings, not the place itself.
      </p>

      <div className="grid gap-4 @3xl:grid-cols-2">
        {plan.weather_note && (
          <section className="rounded-2xl border border-line bg-surface p-4">
            <h3 className="flex items-center gap-2 font-semibold"><CloudSun className="size-4 text-accent" /> Weather</h3>
            <p className="mt-2 text-sm text-muted">{plan.weather_note}</p>
          </section>
        )}
        {plan.packing.length > 0 && (
          <section className="rounded-2xl border border-line bg-surface p-4">
            <h3 className="flex items-center gap-2 font-semibold"><Backpack className="size-4 text-accent" /> Packing list</h3>
            <ul className="mt-2 grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
              {plan.packing.map(p => (
                <li key={p}><label className="flex cursor-pointer items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--accent)]" />{p}</label></li>
              ))}
            </ul>
          </section>
        )}
        {plan.tips.length > 0 && (
          <section className="rounded-2xl border border-line bg-surface p-4 @3xl:col-span-2">
            <h3 className="flex items-center gap-2 font-semibold"><Lightbulb className="size-4 text-accent" /> Local tips</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{plan.tips.map(t => <li key={t}>{t}</li>)}</ul>
          </section>
        )}
      </div>
    </div>
  )
}
