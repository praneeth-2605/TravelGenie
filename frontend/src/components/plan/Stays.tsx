import { useState } from 'react'
import { BedDouble, Check, ExternalLink, Loader2, MapPin, X } from 'lucide-react'
import { nightlyRange, TIER_META, tripStart, type Tier, type TripPlan } from '../../lib/api'
import { stayLinks } from '../../lib/links'
import { LinkButtons } from './LinkButtons'
import { PlacePhoto } from './PlacePhoto'
import { TierTabs } from './Timeline'

/** Hotel chooser: real listings per option, with photos. The itinerary follows the traveller's pick. */
export function Stays({ plan, selected, onChoose }: {
  plan: TripPlan
  selected: Tier
  /** Omitted on read-only views (shared trips). */
  onChoose?: (tier: Tier, placeId: string | null) => Promise<void>
}) {
  const [tier, setTier] = useState<Tier>(selected)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const o = plan.options.find(x => x.tier === tier)
  if (!o) return null
  const picked = plan.hotels?.[tier] ?? null
  const nights = Math.max((plan.schedules?.[tier]?.length ?? plan.days.length) - 1, 1)
  const range = nightlyRange(o, plan.currency)

  const choose = async (id: string | null) => {
    if (!onChoose) return
    setBusy(id ?? 'clear')
    setError(null)
    try { await onChoose(tier, id) } catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }

  return (
    <div className="space-y-5">
      <TierTabs plan={plan} tier={tier} onChange={setTier} />

      <section className="rounded-2xl border border-line bg-surface p-4">
        <div className="text-sm text-muted">{TIER_META[tier].emoji} {o.label} · recommended</div>
        <h3 className="mt-0.5 font-serif text-xl font-semibold">{o.stay.kind.charAt(0).toUpperCase() + o.stay.kind.slice(1)} in {o.stay.area}</h3>
        <div className="mt-1 flex flex-wrap gap-x-3 text-sm text-muted">
          {range && <span className="font-medium text-ink">{range}</span>}
          <span>{nights} night{nights === 1 ? '' : 's'}</span>
        </div>
        {o.stay.why && <p className="mt-2 text-sm leading-relaxed text-muted">{o.stay.why}</p>}
        <p className="mt-2 text-xs text-faint">
          {picked
            ? 'Your itinerary starts and ends each day at the hotel you picked, with real travel times from there.'
            : `Pick a place below and your itinerary is re-timed around it. Until then it just says “your hotel in ${o.stay.area}”.`}
        </p>
      </section>

      {error && <div role="alert" className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>}

      {o.stay.candidates.length === 0 ? (
        <p className="rounded-2xl border border-line bg-surface p-6 text-muted">
          No listed stays were found for this price range. Search the recommended area on Booking.com or Google Maps.
        </p>
      ) : (
        <div className="grid gap-4 @2xl:grid-cols-2 @5xl:grid-cols-3">
          {o.stay.candidates.map(s => {
            const isPicked = picked === s.id
            return (
              <article key={s.id} className={`flex flex-col overflow-hidden rounded-2xl border bg-surface ${isPicked ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'}`}>
                <PlacePhoto place={s} size="url" className="aspect-[16/9] w-full" />
                <div className="flex flex-1 flex-col p-4">
                  <div className="flex items-start gap-2">
                    <BedDouble className="mt-0.5 size-4 shrink-0 text-muted" />
                    <h4 className="min-w-0 flex-1 font-semibold leading-snug">{s.name}</h4>
                    {isPicked && <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-accent-ink"><Check className="size-3" /> Your stay</span>}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
                    {s.area && <span className="flex items-center gap-0.5"><MapPin className="size-3" />{s.area}</span>}
                    {s.price && <span className="font-medium text-ink">{s.price}</span>}
                    {s.tier && <span className="capitalize text-faint">{s.tier === 'mid' ? 'mid-range' : s.tier}</span>}
                  </div>
                  {s.description && <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted">{s.description}</p>}
                  <div className="mt-auto pt-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <LinkButtons links={stayLinks(s.name, s.area, plan.trip.destination ?? '', tripStart(plan), nights, plan.travelers)} />
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-xs font-medium text-accent hover:border-accent/60">
                          Website <ExternalLink className="size-3" />
                        </a>
                      )}
                    </div>
                    {onChoose && (
                      isPicked ? (
                        <button type="button" onClick={() => choose(null)} disabled={busy != null}
                          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-line px-3 py-2 text-sm text-muted hover:text-ink disabled:opacity-60">
                          {busy === 'clear' ? <Loader2 className="size-4 animate-spin" /> : <X className="size-4" />} Undo choice
                        </button>
                      ) : (
                        <button type="button" onClick={() => choose(s.id)} disabled={busy != null}
                          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl border border-accent/60 px-3 py-2 text-sm font-semibold text-accent transition hover:bg-accent hover:text-accent-ink disabled:opacity-60">
                          {busy === s.id ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
                          {busy === s.id ? 'Re-timing your days…' : 'Stay here'}
                        </button>
                      )
                    )}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}
      <p className="text-xs text-faint">
        Listings © Wikivoyage contributors (CC BY-SA); photos © Wikimedia Commons. Listed prices can be out of date, so open
        Booking.com or Google Maps for today's price and the hotel's own photos.
      </p>
    </div>
  )
}
