import { BedDouble, Check, ExternalLink, MapPin, TriangleAlert } from 'lucide-react'
import { money, TIER_META, type PlanOption, type Tier, type TripPlan } from '../../lib/api'

const SEGMENTS: { key: keyof PlanOption['breakdown']; label: string; color: string }[] = [
  { key: 'stay', label: 'Stay', color: 'bg-accent' },
  { key: 'food', label: 'Food', color: 'bg-[#d9a441]' },
  { key: 'transport', label: 'Transport', color: 'bg-[#4f8f86]' },
  { key: 'activities', label: 'Activities', color: 'bg-[#6c7fc2]' },
  { key: 'other', label: 'Other', color: 'bg-faint' },
]

function BreakdownBar({ o, currency }: { o: PlanOption; currency: string }) {
  const total = SEGMENTS.reduce((a, s) => a + (o.breakdown[s.key] || 0), 0) || 1
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-surface-2" role="img"
        aria-label={SEGMENTS.map(s => `${s.label} ${money(o.breakdown[s.key], currency)}`).join(', ')}>
        {SEGMENTS.map(s => (
          <div key={s.key} className={s.color} style={{ width: `${((o.breakdown[s.key] || 0) / total) * 100}%` }} />
        ))}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        {SEGMENTS.filter(s => o.breakdown[s.key]).map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <span className={`size-2 rounded-full ${s.color}`} />
            <dt className="text-muted">{s.label}</dt>
            <dd className="ml-auto font-medium tabular-nums">{money(o.breakdown[s.key], currency)}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function OptionCard({ o, plan, selected, onSelect }: { o: PlanOption; plan: TripPlan; selected: boolean; onSelect: () => void }) {
  const meta = TIER_META[o.tier]
  const cur = plan.currency
  const place = o.stay.place
  const budgetMax = plan.trip.budget_max
  return (
    <article
      onClick={onSelect}
      className={`relative flex cursor-pointer flex-col rounded-2xl border bg-surface p-5 transition ${selected ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line hover:border-accent/40'}`}
    >
      {o.tier === 'yours' && (
        <span className="absolute -top-2.5 left-5 rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-accent-ink">Matched to you</span>
      )}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-muted">{meta.emoji} {o.label}</div>
          <h3 className="mt-0.5 font-serif text-xl leading-tight font-semibold">{o.title}</h3>
        </div>
        <button type="button" onClick={e => { e.stopPropagation(); onSelect() }} aria-pressed={selected}
          aria-label={`Select ${o.label} option`}
          className={`grid size-6 shrink-0 place-items-center rounded-full border-2 ${selected ? 'border-accent bg-accent text-accent-ink' : 'border-line'}`}>
          {selected && <Check className="size-3.5" />}
        </button>
      </div>

      <div className="mt-4">
        <div className="text-3xl font-semibold tracking-tight tabular-nums">{money(o.total, cur)}</div>
        <div className="mt-0.5 text-xs text-muted">
          {money(o.per_person, cur)} per person · {money(o.per_day, cur)} per day
        </div>
        {o.tier === 'yours' && o.fits_budget != null && (
          <div className={`mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${o.fits_budget ? 'bg-ok/15 text-ok' : 'bg-warn/15 text-warn'}`}>
            {o.fits_budget ? <Check className="size-3" /> : <TriangleAlert className="size-3" />}
            {o.fits_budget ? 'Fits your budget' : 'Over your budget'}
            {budgetMax ? ` (${plan.trip.budget_min ? `${money(plan.trip.budget_min, cur)}–` : 'up to '}${money(budgetMax, cur)})` : ''}
          </div>
        )}
      </div>

      <div className="mt-4"><BreakdownBar o={o} currency={cur} /></div>

      <div className="mt-4 rounded-xl bg-surface-2 p-3">
        <div className="flex items-start gap-2.5">
          <BedDouble className="mt-0.5 size-4 shrink-0 text-accent" />
          <div className="min-w-0">
            <div className="font-medium leading-snug">{o.stay.name}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              {place?.area && <span className="flex items-center gap-0.5"><MapPin className="size-3" />{place.area}</span>}
              {o.stay.nightly ? <span>{money(o.stay.nightly, cur)}/night</span> : null}
              {place?.price && <span className="text-faint">listed: {place.price}</span>}
            </div>
            {o.stay.why && <p className="mt-1.5 text-xs leading-relaxed text-muted">{o.stay.why}</p>}
            {place?.url && (
              <a href={place.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
                Website <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        </div>
      </div>

      {o.highlights.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {o.highlights.map(h => (
            <li key={h} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-ok" /><span>{h}</span></li>
          ))}
        </ul>
      )}
      {o.note && <p className="mt-3 text-xs text-muted italic">{o.note}</p>}
    </article>
  )
}

export function Options({ plan, selected, onSelect }: { plan: TripPlan; selected: Tier; onSelect: (t: Tier) => void }) {
  return (
    <div className="space-y-5">
      {plan.answer && (
        <div className="rounded-2xl border border-accent/30 bg-accent-soft/40 p-4 text-[15px] font-medium">{plan.answer}</div>
      )}
      <div>
        <p className="text-[15px] leading-relaxed">{plan.summary}</p>
        {plan.assumptions.length > 0 && (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer hover:text-ink">Assumptions ({plan.assumptions.length})</summary>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4">{plan.assumptions.map(a => <li key={a}>{a}</li>)}</ul>
          </details>
        )}
      </div>
      <div className="grid gap-4 pt-1 xl:grid-cols-3">
        {plan.options.map(o => (
          <OptionCard key={o.tier} o={o} plan={plan} selected={selected === o.tier} onSelect={() => onSelect(o.tier)} />
        ))}
      </div>
      <p className="text-xs text-faint">
        All three options share the same sightseeing plan; they differ in stay, food, transport and extras.
        Prices are estimates from guide listings; check before booking.
      </p>
    </div>
  )
}
