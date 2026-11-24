import { Backpack, Clock, CloudSun, ExternalLink, Lightbulb, MapPin, Moon, Sun, Sunrise, Sunset } from 'lucide-react'
import { money, type TripPlan } from '../../lib/api'
import { mapsPlace } from '../../lib/links'

function slotIcon(time: string) {
  const t = time.toLowerCase()
  if (t.includes('morning')) return Sunrise
  if (t.includes('afternoon')) return Sun
  if (t.includes('evening')) return Sunset
  if (t.includes('night')) return Moon
  return Clock
}

export const DAY_COLORS = ['#c8603f', '#4f8f86', '#6c7fc2', '#d9a441', '#9b5fa8', '#3f7cb8', '#b8574f', '#5e9c4c', '#c47a2c', '#7a6a58']

export function Timeline({ plan, onCite, onShowOnMap }: { plan: TripPlan; onCite: (n: number) => void; onShowOnMap: (placeId: string) => void }) {
  const cur = plan.currency
  return (
    <div className="space-y-5">
      {plan.days.map(d => {
        const color = DAY_COLORS[(d.day - 1) % DAY_COLORS.length]
        const date = d.date ? new Date(`${d.date}T12:00:00`) : null
        return (
          <section key={d.day} className="overflow-hidden rounded-2xl border border-line bg-surface">
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
                </div>
              </div>
            </header>
            <ol className="relative px-4 py-3">
              {d.items.map((it, i) => {
                const Icon = slotIcon(it.time)
                return (
                  <li key={i} className="relative flex gap-3 pb-4 last:pb-1">
                    {i < d.items.length - 1 && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-line" aria-hidden />}
                    <span className="z-10 grid size-8 shrink-0 place-items-center rounded-full border border-line bg-surface">
                      <Icon className="size-4" style={{ color }} />
                    </span>
                    <div className="min-w-0 flex-1 pt-0.5">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-xs font-semibold tracking-wide uppercase" style={{ color }}>{it.time}</span>
                        <span className="font-medium">{it.title}</span>
                        {it.cite?.map(n => (
                          <button key={n} type="button" onClick={() => onCite(n)}
                            className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-accent-soft px-1 font-mono text-[10px] text-accent hover:bg-accent hover:text-accent-ink">
                            {n}
                          </button>
                        ))}
                        {it.cost ? <span className="ml-auto text-xs text-muted tabular-nums">{money(it.cost, cur)}</span> : null}
                      </div>
                      {it.description && <p className="mt-0.5 text-sm leading-relaxed text-muted">{it.description}</p>}
                      {it.place && (
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-faint">
                          {it.place.hours && <span className="flex items-center gap-1"><Clock className="size-3" />{it.place.hours}</span>}
                          {it.place.price && <span>{it.place.price}</span>}
                          {it.place.lat != null && (
                            <button type="button" onClick={() => onShowOnMap(it.place!.id)} className="flex items-center gap-1 font-medium text-accent hover:underline">
                              <MapPin className="size-3" /> Show on map
                            </button>
                          )}
                          <a href={mapsPlace(it.place.name, it.place.area, plan.trip.destination)} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1 font-medium text-accent hover:underline">
                            Google Maps <ExternalLink className="size-3" />
                          </a>
                        </div>
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
          </section>
        )
      })}

      <div className="grid gap-4 md:grid-cols-2">
        {plan.weather_note && (
          <section className="rounded-2xl border border-line bg-surface p-4">
            <h3 className="flex items-center gap-2 font-semibold"><CloudSun className="size-4 text-accent" /> Weather</h3>
            {plan.weather && (
              <div className="mt-3 grid grid-cols-5 gap-1.5">
                {plan.weather.daily.slice(0, 5).map(w => (
                  <div key={w.date} className="rounded-lg bg-surface-2 py-2 text-center" title={w.condition}>
                    <div className="text-[11px] text-faint">{new Date(`${w.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' })}</div>
                    <div className="text-sm font-semibold">{Math.round(w.max_c)}°</div>
                    <div className="text-[11px] text-faint">{Math.round(w.min_c)}°</div>
                  </div>
                ))}
              </div>
            )}
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
          <section className="rounded-2xl border border-line bg-surface p-4 md:col-span-2">
            <h3 className="flex items-center gap-2 font-semibold"><Lightbulb className="size-4 text-accent" /> Local tips</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{plan.tips.map(t => <li key={t}>{t}</li>)}</ul>
          </section>
        )}
      </div>
    </div>
  )
}
