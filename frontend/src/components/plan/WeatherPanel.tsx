import { Cloud, CloudRain, CloudSun, Droplets, Sun, Thermometer } from 'lucide-react'
import { tripStart, type TripPlan } from '../../lib/api'

export function weatherIcon(condition: string) {
  const c = condition.toLowerCase()
  if (c.includes('rain') || c.includes('drizzle') || c.includes('thunder')) return CloudRain
  if (c.includes('cloud')) return Cloud
  if (c.includes('clear')) return Sun
  return CloudSun
}

export function WeatherPanel({ plan }: { plan: TripPlan }) {
  const w = plan.weather
  const start = tripStart(plan)
  return (
    <div className="space-y-5">
      {w ? (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="font-serif text-2xl font-semibold">Live forecast · {w.location}</h2>
          <p className="mt-0.5 text-xs text-faint">Fetched {w.fetched_at}</p>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {w.daily.slice(0, 5).map(d => {
              const Icon = weatherIcon(d.condition)
              return (
                <div key={d.date} className="rounded-xl bg-surface-2 p-3 text-center">
                  <div className="text-xs text-muted">{new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                  <Icon className="mx-auto my-2 size-8 text-accent" />
                  <div className="text-lg font-semibold">{Math.round(d.max_c)}° <span className="text-sm font-normal text-faint">/ {Math.round(d.min_c)}°</span></div>
                  <div className="text-xs text-muted">{d.condition}</div>
                  {d.rain_mm > 0 && <div className="mt-1 flex items-center justify-center gap-0.5 text-xs text-[#3f7cb8]"><Droplets className="size-3" />{d.rain_mm} mm</div>}
                </div>
              )
            })}
          </div>
        </section>
      ) : (
        <section className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-5">
          <Thermometer className="mt-0.5 size-5 shrink-0 text-accent" />
          <div>
            <h2 className="font-semibold">Seasonal outlook</h2>
            <p className="mt-0.5 text-sm text-muted">
              {start ? `Your trip starts ${new Date(`${start}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })}, beyond the 5-day live forecast, so this is based on typical weather for that time of year.`
                : 'No dates yet, so this is based on typical weather.'}
            </p>
          </div>
        </section>
      )}
      {plan.weather_note && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h3 className="flex items-center gap-2 font-semibold"><CloudSun className="size-4 text-accent" /> What to expect</h3>
          <p className="mt-2 text-[15px] leading-relaxed">{plan.weather_note}</p>
        </section>
      )}
      {plan.packing.length > 0 && (
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h3 className="font-semibold">🎒 Pack for the weather</h3>
          <ul className="mt-2 grid gap-1.5 text-sm sm:grid-cols-2">
            {plan.packing.map(p => (
              <li key={p}><label className="flex cursor-pointer items-start gap-2"><input type="checkbox" className="mt-1 accent-[var(--accent)]" />{p}</label></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
