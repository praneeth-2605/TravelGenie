import { ArrowRight, BedDouble, Car, Check, Loader2, MapPin, TriangleAlert } from 'lucide-react'
import { money, nightlyRange, pickedHotel, stayLabel, TIER_META, type PlanOption, type Tier, type TripPlan } from '../../lib/api'
import { PlacePhoto } from './PlacePhoto'
import { MODE_ICON } from './GettingThere'

const SEGMENTS: { key: keyof PlanOption['breakdown']; label: string; color: string }[] = [
  { key: 'travel', label: 'Getting there', color: 'bg-[#3f7cb8]' },
  { key: 'stay', label: 'Stay', color: 'bg-accent' },
  { key: 'food', label: 'Food', color: 'bg-[#d9a441]' },
  { key: 'transport', label: 'Local transport', color: 'bg-[#4f8f86]' },
  { key: 'activities', label: 'Activities', color: 'bg-[#6c7fc2]' },
  { key: 'other', label: 'Other', color: 'bg-faint' },
]

export function BreakdownBar({ o, currency }: { o: PlanOption; currency: string }) {
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

interface CardProps {
  o: PlanOption
  plan: TripPlan
  selected: boolean
  choosing: boolean
  disabled: boolean
  onChoose?: () => void
}

function OptionCard({ o, plan, selected, choosing, disabled, onChoose }: CardProps) {
  const meta = TIER_META[o.tier]
  const cur = plan.currency
  const hotel = pickedHotel(plan, o.tier)
  const range = nightlyRange(o, cur)
  const preview = hotel ?? o.stay.candidates.find(c => c.photo) ?? null
  const budgetMax = plan.trip.budget_max
  const gt = o.getting_there
  const GtIcon = gt ? MODE_ICON[gt.mode as keyof typeof MODE_ICON] ?? Car : null
  return (
    <article
      className={`relative flex flex-col rounded-2xl border bg-surface p-5 transition ${selected ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'}`}
    >
      {selected ? (
        <span className="absolute -top-2.5 left-5 flex items-center gap-1 rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-accent-ink"><Check className="size-3" /> Your plan</span>
      ) : o.tier === 'yours' && (
        <span className="absolute -top-2.5 left-5 rounded-full bg-ink px-2.5 py-0.5 text-[11px] font-semibold text-bg">Matched to you</span>
      )}
      <div>
        <div className="text-sm font-medium text-muted">{meta.emoji} {o.label}</div>
        <h3 className="mt-0.5 font-serif text-xl leading-tight font-semibold">{o.title}</h3>
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

      {gt && GtIcon && (
        <div className="mt-4 flex items-start gap-2.5 rounded-xl bg-surface-2 p-3">
          <GtIcon className="mt-0.5 size-4 shrink-0 text-accent" />
          <div className="min-w-0 text-sm">
            <div className="font-medium capitalize">{gt.mode}{gt.duration ? ` · ${gt.duration}` : ''}</div>
            <div className="text-xs text-muted">{gt.detail}{gt.cost ? ` · ${money(gt.cost, cur)} return` : ''}</div>
          </div>
        </div>
      )}

      <div className="mt-3 rounded-xl bg-surface-2 p-3">
        <div className="flex items-start gap-2.5">
          {preview ? <PlacePhoto place={preview} label={false} className="size-12 shrink-0 rounded-lg" /> : <BedDouble className="mt-0.5 size-4 shrink-0 text-accent" />}
          <div className="min-w-0">
            <div className="font-medium leading-snug">{stayLabel(plan, o)}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              <span className="flex items-center gap-0.5"><MapPin className="size-3" />{hotel?.area ?? o.stay.area}</span>
              {range && <span>{range}</span>}
              {!hotel && o.stay.candidates.length > 0 && <span className="text-faint">{o.stay.candidates.length} hotels to choose from</span>}
            </div>
            {o.stay.why && <p className="mt-1.5 text-xs leading-relaxed text-muted">{o.stay.why}</p>}
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
      {onChoose && <div className="mt-auto pt-5">
        <button type="button" onClick={onChoose} disabled={disabled}
          className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60 ${selected ? 'bg-accent text-accent-ink' : 'border border-accent/60 text-accent hover:bg-accent hover:text-accent-ink'}`}>
          {choosing && <Loader2 className="size-4 animate-spin" />}
          {choosing ? 'Building your detailed plan…' : selected ? 'Open my plan' : `Choose ${o.label}`}
          {!choosing && <ArrowRight className="size-4" />}
        </button>
      </div>}
    </article>
  )
}

export function Options({ plan, selected, choosing, onChoose }: {
  plan: TripPlan; selected: Tier | null; choosing: Tier | null; onChoose?: (t: Tier) => void
}) {
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
      <div className="grid gap-4 pt-1 @3xl:grid-cols-3">
        {plan.options.map(o => (
          <OptionCard key={o.tier} o={o} plan={plan} selected={selected === o.tier} choosing={choosing === o.tier}
            disabled={choosing != null} onChoose={onChoose ? () => onChoose(o.tier) : undefined} />
        ))}
      </div>
      <p className="text-xs text-faint">
        All three options share the same sightseeing plan; they differ in how you travel, where you stay, food and extras.
        Choose one for a booking checklist and money tips, pick your hotel in Stays, then discuss it in the chat.
        Prices are estimates; check before booking.
      </p>
    </div>
  )
}
