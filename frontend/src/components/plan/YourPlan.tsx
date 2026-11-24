import { ArrowRight, BedDouble, Car, ExternalLink, Loader2, MapPin, MessageCircle, Repeat, Sparkles } from 'lucide-react'
import { money, nightlyRange, pickedHotel, stayLabel, TIER_META, tripStart, type Tier, type TripPlan } from '../../lib/api'
import { PlacePhoto } from './PlacePhoto'
import { BreakdownBar } from './Options'
import { MODE_ICON } from './GettingThere'
import { DAY_COLORS, duration } from './Timeline'
import { LinkButtons } from './LinkButtons'
import { stayLinks, transportLinks } from '../../lib/links'

export function YourPlan({ plan, tier, choosing, onRebuild, onAsk, onSwitch, onOpenStays, onOpenItinerary }: {
  plan: TripPlan
  tier: Tier
  choosing: boolean
  onRebuild: () => void
  onAsk: (question: string) => void
  onSwitch: () => void
  onOpenStays: () => void
  onOpenItinerary: () => void
}) {
  const o = plan.options.find(x => x.tier === tier)
  if (!o) return null
  const cur = plan.currency
  const meta = TIER_META[tier]
  const det = o.details
  const gt = o.getting_there
  const GtIcon = gt ? MODE_ICON[gt.mode as keyof typeof MODE_ICON] ?? Car : null
  const hotel = pickedHotel(plan, tier)
  const schedule = plan.schedules?.[tier] ?? []
  const nights = Math.max(schedule.length - 1, 1)
  const destination = plan.trip.destination ?? ''
  const origin = plan.transport?.origin ?? plan.trip.origin ?? ''

  const questions = [
    'What should I book first, and when?',
    `How can I make this ${meta.planName} a bit cheaper?`,
    hotel ? `What's good to eat near ${hotel.name}?` : `Which of the hotels in ${o.stay.area} would you pick for us, and why?`,
    gt ? `Is ${gt.mode} really the best way to get there for us?` : 'What is the best way to get there?',
  ]

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="overflow-hidden rounded-2xl border border-accent/40 bg-surface">
        <div className="bg-gradient-to-br from-accent/15 via-transparent to-transparent p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-accent">{meta.emoji} Your plan · {meta.label}</div>
              <h2 className="mt-1 font-serif text-3xl font-semibold tracking-tight">{o.title}</h2>
            </div>
            <button type="button" onClick={onSwitch} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-muted hover:text-ink">
              <Repeat className="size-4" /> Switch plan
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <div className="text-4xl font-semibold tracking-tight tabular-nums">{money(o.total, cur)}</div>
              <div className="text-sm text-muted">{money(o.per_person, cur)} per person · {plan.travelers} traveller{plan.travelers === 1 ? '' : 's'} · {schedule.length || plan.days.length} days</div>
            </div>
          </div>
          <div className="mt-5 max-w-xl"><BreakdownBar o={o} currency={cur} /></div>
        </div>

        <div className="grid gap-px bg-line @xl:grid-cols-2">
          <div className="bg-surface p-5">
            <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-faint uppercase">{GtIcon && <GtIcon className="size-4 text-accent" />} Getting there</div>
            {gt ? (
              <>
                <div className="mt-1.5 font-medium capitalize">{gt.mode}{gt.duration ? ` · ${gt.duration}` : ''}</div>
                <p className="text-sm text-muted">{gt.detail}</p>
                {gt.arrive_at && <p className="text-sm text-muted">Arrive at <strong className="text-ink">{gt.arrive_at}</strong>{gt.arrive_time ? ` around ${gt.arrive_time}` : ''}</p>}
                {gt.cost ? <p className="mt-1 text-sm font-medium tabular-nums">{money(gt.cost, cur)} return for everyone</p> : null}
                {origin && destination && (
                  <LinkButtons className="mt-2" links={transportLinks(gt.mode, origin, destination, tripStart(plan), plan.travelers)} />
                )}
              </>
            ) : <p className="mt-1.5 text-sm text-muted">Add your starting city to plan the journey.</p>}
          </div>
          <div className="bg-surface p-5">
            <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-faint uppercase"><BedDouble className="size-4 text-accent" /> Where you'll stay</div>
            {hotel ? (
              <div className="mt-1.5 flex gap-3">
                <PlacePhoto place={hotel} label={false} className="size-16 shrink-0 rounded-lg" />
                <div className="min-w-0">
                  <div className="font-medium">{hotel.name}</div>
                  <div className="flex flex-wrap gap-x-3 text-sm text-muted">
                    {hotel.area && <span className="flex items-center gap-0.5"><MapPin className="size-3.5" />{hotel.area}</span>}
                    {hotel.price && <span>{hotel.price}</span>}
                  </div>
                  {hotel.url && <a href={hotel.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">Website <ExternalLink className="size-3.5" /></a>}
                </div>
              </div>
            ) : (
              <>
                <div className="mt-1.5 font-medium">{stayLabel(plan, o)}</div>
                <div className="text-sm text-muted">{nightlyRange(o, cur) ?? ''}{o.stay.candidates.length ? ` · ${o.stay.candidates.length} hotels to choose from` : ''}</div>
              </>
            )}
            {o.stay.why && <p className="mt-1 text-sm text-muted">{o.stay.why}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" onClick={onOpenStays}
                className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-ink hover:opacity-90">
                {hotel ? 'Change hotel' : 'Choose your hotel'} <ArrowRight className="size-3" />
              </button>
              {hotel && <LinkButtons links={stayLinks(hotel.name, hotel.area, destination, tripStart(plan), nights, plan.travelers)} />}
            </div>
          </div>
        </div>
      </section>

      {!det ? (
        <section className="rounded-2xl border border-line bg-surface p-6 text-center">
          <p className="text-muted">The plan changed since you chose it. Rebuild the detailed version (meals, daily spend, bookings).</p>
          <button type="button" onClick={onRebuild} disabled={choosing}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60">
            {choosing ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Build detailed plan
          </button>
        </section>
      ) : (
        <>
          <p className="text-[15px] leading-relaxed">{det.overview}</p>

          {/* Ask about it */}
          <section className="rounded-2xl border border-line bg-surface-2/50 p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold"><MessageCircle className="size-4 text-accent" /> Ask about your plan</h3>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {questions.map(q => (
                <button key={q} type="button" onClick={() => onAsk(q)}
                  className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-sm hover:border-accent/60 hover:text-accent">
                  {q}
                </button>
              ))}
            </div>
          </section>

          {/* Day by day, at a glance (full detail with photos is in the Itinerary tab) */}
          <section className="space-y-4">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-lg font-semibold">Day by day</h3>
              <button type="button" onClick={onOpenItinerary} className="text-sm font-medium text-accent hover:underline">Full itinerary with photos</button>
            </div>
            {schedule.map(d => {
              const color = DAY_COLORS[(d.day - 1) % DAY_COLORS.length]
              return (
                <article key={d.day} className="overflow-hidden rounded-2xl border border-line bg-surface">
                  <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
                    <span className="grid size-9 place-items-center rounded-lg text-sm font-semibold text-white" style={{ background: color }}>{d.day}</span>
                    <div className="min-w-0 flex-1">
                      <h4 className="font-semibold">{d.title}</h4>
                      <div className="text-xs text-muted">
                        {d.date && new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
                        {d.area ? ` · ${d.area}` : ''}
                      </div>
                    </div>
                  </header>
                  <ul className="divide-y divide-line/60 px-4 py-1">
                    {d.steps.map((st, i) => st.kind === 'travel' ? (
                      <li key={i} className="flex gap-3 py-1 pl-14 text-xs text-faint">
                        <Car className="size-3.5 shrink-0" /> {st.title.split(' to ')[0]} · {st.distance_km} km · {duration(st.minutes)}
                      </li>
                    ) : (
                      <li key={i} className="flex gap-3 py-1.5 text-sm">
                        <span className="w-11 shrink-0 font-medium tabular-nums" style={{ color }}>{st.time}</span>
                        <span className="min-w-0 flex-1">{st.title}{st.minutes ? <span className="text-faint"> · {duration(st.minutes)}</span> : null}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              )
            })}
          </section>

          {/* Booking checklist */}
          {det.booking_checklist.length > 0 && (
            <section className="rounded-2xl border border-line bg-surface p-5">
              <h3 className="text-lg font-semibold">Booking checklist</h3>
              <p className="text-sm text-muted">In the order to do them.</p>
              <ul className="mt-3 divide-y divide-line">
                {det.booking_checklist.map((b, i) => (
                  <li key={i} className="py-2.5">
                    <label className="flex cursor-pointer items-start gap-3">
                      <input type="checkbox" className="mt-1 size-4 accent-[var(--accent)]" />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{b.item}</span>
                        <span className="block text-sm text-muted">{b.when} · {b.where}</span>
                      </span>
                      {b.cost ? <span className="shrink-0 text-sm font-medium tabular-nums">{money(b.cost, cur)}</span> : null}
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="grid gap-4 @xl:grid-cols-2">
            {det.money_tips.length > 0 && (
              <section className="rounded-2xl border border-line bg-surface p-5">
                <h3 className="font-semibold">💸 Money tips</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{det.money_tips.map(t => <li key={t}>{t}</li>)}</ul>
              </section>
            )}
            {det.good_to_know.length > 0 && (
              <section className="rounded-2xl border border-line bg-surface p-5">
                <h3 className="font-semibold">📌 Good to know</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{det.good_to_know.map(t => <li key={t}>{t}</li>)}</ul>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  )
}
