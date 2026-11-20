import { BusFront, Car, Clock, ExternalLink, Plane, Ship, TrainFront, X } from 'lucide-react'
import { money, TIER_META, type TransportMode, type TripPlan } from '../../lib/api'

export const MODE_ICON = { flight: Plane, train: TrainFront, bus: BusFront, car: Car, ferry: Ship } as const
const MODE_NAME = { flight: 'Flight', train: 'Train', bus: 'Bus', car: 'Car', ferry: 'Ferry' } as const

export function priceRange(m: TransportMode, currency: string) {
  if (m.price_min == null && m.price_max == null) return '—'
  if (m.price_max == null || m.price_min === m.price_max) return money(m.price_min ?? m.price_max, currency)
  return `${money(m.price_min, currency)} – ${money(m.price_max, currency)}`
}

const BEST: Record<string, string> = { budget: 'Cheapest', speed: 'Fastest', comfort: 'Most comfortable', balanced: 'Best balance' }

export function GettingThere({ plan }: { plan: TripPlan }) {
  const t = plan.transport
  if (!t || !t.modes?.length) {
    return (
      <div className="rounded-2xl border border-line bg-surface p-6 text-muted">
        <p className="font-medium text-ink">Where are you starting from?</p>
        <p className="mt-1 text-sm">Tell me in the chat (e.g. "I'm travelling from Hyderabad") or set your home city in Settings, and I'll compare flights, trains, buses and driving.</p>
      </div>
    )
  }
  const available = t.modes.filter(m => m.available)
  const unavailable = t.modes.filter(m => !m.available)
  const picks = new Map<string, string[]>()
  plan.options.forEach(o => {
    if (o.getting_there?.mode) picks.set(o.getting_there.mode, [...(picks.get(o.getting_there.mode) ?? []), o.tier])
  })
  // Cheapest first.
  available.sort((a, b) => (a.price_min ?? Infinity) - (b.price_min ?? Infinity))

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="font-serif text-2xl font-semibold">{t.origin} → {t.destination}</h2>
          {t.distance_km && <span className="text-sm text-muted">~{t.distance_km.toLocaleString()} km as the crow flies</span>}
        </div>
        <p className="mt-2 text-[15px] leading-relaxed">{t.summary}</p>
        {t.recommendation && <p className="mt-2 rounded-xl bg-accent-soft/40 px-3 py-2 text-sm"><strong>Our take:</strong> {t.recommendation}</p>}
      </div>

      <div className="grid gap-4 @xl:grid-cols-2">
        {available.map((m, i) => {
          const Icon = MODE_ICON[m.mode] ?? Car
          const tiers = picks.get(m.mode) ?? []
          return (
            <article key={`${m.mode}-${i}`} className="flex flex-col rounded-2xl border border-line bg-surface p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><Icon className="size-5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <h3 className="text-lg font-semibold">{MODE_NAME[m.mode]}{m.label ? ` · ${m.label}` : ''}</h3>
                    {m.best_for && BEST[m.best_for] && (
                      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">{BEST[m.best_for]}</span>
                    )}
                  </div>
                  {m.route && <div className="mt-0.5 text-sm text-muted">{m.route}</div>}
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl bg-surface-2 px-3 py-2">
                  <dt className="text-xs text-faint">Price per person, one way</dt>
                  <dd className="font-semibold tabular-nums">{priceRange(m, t.currency)}</dd>
                </div>
                <div className="rounded-xl bg-surface-2 px-3 py-2">
                  <dt className="flex items-center gap-1 text-xs text-faint"><Clock className="size-3" /> Duration</dt>
                  <dd className="font-semibold">{m.duration ?? '—'}</dd>
                </div>
              </dl>
              {m.frequency && <p className="mt-3 text-sm text-muted">🕒 {m.frequency}</p>}
              {(m.pros || m.cons) && (
                <div className="mt-2 space-y-1 text-sm">
                  {m.pros && <p><span className="text-ok">＋</span> {m.pros}</p>}
                  {m.cons && <p><span className="text-bad">－</span> {m.cons}</p>}
                </div>
              )}
              <div className="mt-auto pt-4">
                {m.book_via.length > 0 && (
                  <p className="text-xs text-muted">Book via <span className="font-medium text-ink">{[...new Set(m.book_via)].join(' · ')}</span></p>
                )}
                {tiers.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {tiers.map(tier => (
                      <span key={tier} className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-accent-ink">
                        {TIER_META[tier as keyof typeof TIER_META]?.emoji} Used in {TIER_META[tier as keyof typeof TIER_META]?.label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </article>
          )
        })}
      </div>

      {unavailable.length > 0 && (
        <div className="rounded-2xl border border-dashed border-line p-4 text-sm text-muted">
          {unavailable.map(m => (
            <p key={m.mode} className="flex items-start gap-2"><X className="mt-0.5 size-4 shrink-0 text-faint" />
              <span><strong className="text-ink">{MODE_NAME[m.mode]}:</strong> not an option{m.cons && m.cons !== 'N/A' ? `: ${m.cons}` : ''}</span></p>
          ))}
        </div>
      )}
      <p className="flex flex-wrap items-center gap-1 text-xs text-faint">
        Prices and times are typical ranges; check live fares before booking.
        {t.guide_url && <a href={t.guide_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent hover:underline">Wikivoyage “Get in” guide <ExternalLink className="size-3" /></a>}
      </p>
    </div>
  )
}
