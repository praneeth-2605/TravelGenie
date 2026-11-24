import { BedDouble, ExternalLink, MapPin } from 'lucide-react'
import { TIER_META, type Place, type Tier, type TripPlan } from '../../lib/api'
import { stayLinks } from '../../lib/links'
import { LinkButtons } from './LinkButtons'

const GROUPS: { tier: Place['tier']; label: string; emoji: string }[] = [
  { tier: 'budget', label: 'Budget · hostels & guesthouses', emoji: '💰' },
  { tier: 'mid', label: 'Mid-range', emoji: '🏨' },
  { tier: 'luxury', label: 'Luxury', emoji: '💎' },
]

export function Stays({ plan, selected }: { plan: TripPlan; selected: Tier }) {
  const chosen = new Map<string, Tier[]>()
  plan.options.forEach(o => {
    const id = o.stay.place?.id
    if (id) chosen.set(id, [...(chosen.get(id) ?? []), o.tier])
  })
  const selectedId = plan.options.find(o => o.tier === selected)?.stay.place?.id

  if (!plan.stay_candidates.length) {
    return <p className="rounded-2xl border border-line bg-surface p-6 text-muted">No stay listings were found for this destination; the options use estimated prices.</p>
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">Real places to stay from Wikivoyage, grouped by price. Picks for each option are marked.</p>
      {GROUPS.map(g => {
        const items = plan.stay_candidates.filter(s => s.tier === g.tier)
        if (!items.length) return null
        return (
          <section key={g.tier}>
            <h3 className="mb-2 text-sm font-semibold">{g.emoji} {g.label} <span className="font-normal text-faint">({items.length})</span></h3>
            <div className="grid gap-3 md:grid-cols-2">
              {items.map(s => {
                const picks = chosen.get(s.id) ?? []
                return (
                  <article key={s.id} className={`rounded-xl border bg-surface p-3.5 ${s.id === selectedId ? 'border-accent' : 'border-line'}`}>
                    <div className="flex items-start gap-2.5">
                      <BedDouble className="mt-0.5 size-4 shrink-0 text-muted" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium">{s.name}</span>
                          {picks.map(t => (
                            <span key={t} className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-semibold text-accent">
                              {TIER_META[t].emoji} {TIER_META[t].label} pick
                            </span>
                          ))}
                        </div>
                        <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted">
                          {s.area && <span className="flex items-center gap-0.5"><MapPin className="size-3" />{s.area}</span>}
                          {s.price && <span className="font-medium text-ink">{s.price}</span>}
                        </div>
                        {s.description && <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted">{s.description}</p>}
                        {s.url && (
                          <a href={s.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
                            Website <ExternalLink className="size-3" />
                          </a>
                        )}
                        <LinkButtons className="mt-2" links={stayLinks(s.name, s.area, plan.trip.destination ?? '',
                          plan.days[0]?.date, Math.max(plan.days.length - 1, 1), plan.travelers)} />
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        )
      })}
      <p className="text-xs text-faint">Listings © Wikivoyage contributors (CC BY-SA). Prices change; confirm when booking.</p>
    </div>
  )
}
