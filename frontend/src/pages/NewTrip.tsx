import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Calendar, CalendarDays, MapPin, Minus, Navigation, Plus, Users, Wallet } from 'lucide-react'
import { money, TIER_META, uid } from '../lib/api'
import { useAuth } from '../lib/auth'

const INTEREST_OPTIONS = ['Beaches', 'Food', 'Temples', 'Museums', 'Nightlife', 'Nature', 'Hiking', 'Shopping', 'History', 'Art', 'Adventure', 'Relaxation']
const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'SGD', 'AED', 'THB', 'IDR']

export function buildPrompt(f: {
  destination: string; origin: string; start: string; days: number; travelers: number; currency: string
  min: string; max: string; perPerson?: boolean; interests: string[]; notes: string
}) {
  const parts = [`Plan ${f.days} days in ${f.destination.trim()}`]
  if (f.origin.trim()) parts.push(`travelling from ${f.origin.trim()}`)
  if (f.start) parts.push(`starting ${f.start}`)
  parts.push(`for ${f.travelers} ${f.travelers === 1 ? 'person' : 'people'}`)
  // The agents work with the TOTAL for everyone; a per-person budget is multiplied out.
  const mult = f.perPerson ? Math.max(f.travelers, 1) : 1
  const lo = f.min ? Number(f.min) * mult : 0
  const hi = f.max ? Number(f.max) * mult : 0
  const pp = f.perPerson && f.travelers > 1
    ? ` (${f.min ? `${f.min} to ` : 'up to '}${f.max || f.min} ${f.currency} per person)` : ''
  if (lo && hi) parts.push(`with a total budget of ${lo} to ${hi} ${f.currency}${pp}`)
  else if (hi) parts.push(`with a total budget of up to ${hi} ${f.currency}${pp}`)
  else parts.push(`(prices in ${f.currency})`)
  let text = parts.join(' ') + '.'
  if (f.interests.length) text += ` We love ${f.interests.join(', ').toLowerCase()}.`
  if (f.notes.trim()) text += ` ${f.notes.trim()}`
  return text
}

export function NewTrip() {
  const { settings } = useAuth()
  const navigate = useNavigate()
  const [destination, setDestination] = useState('')
  const [origin, setOrigin] = useState(settings?.home_city ?? '')
  const [start, setStart] = useState('')
  const [days, setDays] = useState(4)
  const [travelers, setTravelers] = useState(settings?.default_travelers ?? 1)
  const [currency, setCurrency] = useState(settings?.home_currency ?? 'INR')
  const [min, setMin] = useState(settings?.budget_min ? String(settings.budget_min) : '')
  const [max, setMax] = useState(settings?.budget_max ? String(settings.budget_max) : '')
  const [perPerson, setPerPerson] = useState(false)
  const [interests, setInterests] = useState<string[]>(
    (settings?.interests ?? []).map(i => i[0].toUpperCase() + i.slice(1)))
  const [notes, setNotes] = useState('')
  const [freeform, setFreeform] = useState('')
  const [error, setError] = useState<string | null>(null)

  const go = (message: string) => navigate(`/trips/${uid()}`, { state: { initialMessage: message } })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!destination.trim()) return setError('Where are you going?')
    if (min && max && Number(min) > Number(max)) return setError('The minimum budget is above the maximum.')
    go(buildPrompt({ destination, origin, start, days, travelers, currency, min, max, perPerson, interests, notes }))
  }

  const toggle = (i: string) => setInterests(s => (s.includes(i) ? s.filter(x => x !== i) : [...s, i]))
  const field = 'w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none'
  const today = new Date().toISOString().slice(0, 10)

  function Stepper({ value, set, lo, hi, label }: { value: number; set: (n: number) => void; lo: number; hi: number; label: string }) {
    return (
      <div className="flex items-center rounded-xl border border-line bg-surface">
        <button type="button" onClick={() => set(Math.max(lo, value - 1))} aria-label={`Fewer ${label}`} className="p-3 text-muted hover:text-ink disabled:opacity-30" disabled={value <= lo}><Minus className="size-4" /></button>
        <span className="flex-1 text-center font-medium tabular-nums">{value}</span>
        <button type="button" onClick={() => set(Math.min(hi, value + 1))} aria-label={`More ${label}`} className="p-3 text-muted hover:text-ink disabled:opacity-30" disabled={value >= hi}><Plus className="size-4" /></button>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-8">
        <p className="text-sm font-medium tracking-[0.16em] text-accent uppercase">New trip</p>
        <h1 className="mt-2 font-serif text-4xl font-semibold tracking-tight">Where to next?</h1>
        <p className="mt-2 text-muted">You'll get three plans: {Object.values(TIER_META).map(t => `${t.emoji} ${t.label}`).join(', ')}, each with stays and a day-by-day itinerary.</p>

        <form onSubmit={submit} className="mt-8 space-y-6 rounded-2xl border border-line bg-surface p-5 sm:p-7">
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-medium"><Navigation className="size-4 text-accent" /> From</span>
              <input className={`${field} mt-2 text-lg`} placeholder="e.g. Hyderabad" value={origin}
                onChange={e => setOrigin(e.target.value)} maxLength={80} autoComplete="address-level2" />
            </label>
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-medium"><MapPin className="size-4 text-accent" /> Destination</span>
              <input className={`${field} mt-2 text-lg`} placeholder="e.g. Goa, Kyoto, Paris, Bali" value={destination}
                onChange={e => setDestination(e.target.value)} autoFocus maxLength={80} />
            </label>
          </div>
          <p className="-mt-3 text-xs text-faint">We'll compare flights, trains, buses and driving from your starting city.</p>

          <div className="grid gap-5 sm:grid-cols-3">
            <label className="block">
              <span className="flex items-center gap-2 text-sm font-medium"><Calendar className="size-4 text-accent" /> Start date</span>
              <input type="date" min={today} className={`${field} mt-2`} value={start} onChange={e => setStart(e.target.value)} />
            </label>
            <div>
              <span className="flex items-center gap-2 text-sm font-medium"><CalendarDays className="size-4 text-accent" /> Days</span>
              <div className="mt-2"><Stepper value={days} set={setDays} lo={1} hi={10} label="days" /></div>
            </div>
            <div>
              <span className="flex items-center gap-2 text-sm font-medium"><Users className="size-4 text-accent" /> Travellers</span>
              <div className="mt-2"><Stepper value={travelers} set={setTravelers} lo={1} hi={20} label="travellers" /></div>
            </div>
          </div>

          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-medium"><Wallet className="size-4 text-accent" /> Your budget range</span>
              <div role="radiogroup" aria-label="Budget is" className="inline-flex rounded-lg border border-line p-0.5 text-xs">
                {([[false, 'Total for everyone'], [true, 'Per person']] as const).map(([value, label]) => (
                  <button key={label} type="button" role="radio" aria-checked={perPerson === value} onClick={() => setPerPerson(value)}
                    className={`rounded-md px-2.5 py-1 ${perPerson === value ? 'bg-surface-2 font-medium text-ink' : 'text-muted'}`}>{label}</button>
                ))}
              </div>
            </div>
            <div className="mt-2 grid grid-cols-[110px_1fr_1fr] gap-2">
              <select aria-label="Currency" className={field} value={currency} onChange={e => setCurrency(e.target.value)}>
                {CURRENCIES.map(c => <option key={c}>{c}</option>)}
              </select>
              <input inputMode="numeric" aria-label="Minimum budget" className={field} placeholder="Min" value={min} onChange={e => setMin(e.target.value.replace(/[^\d]/g, ''))} />
              <input inputMode="numeric" aria-label="Maximum budget" className={field} placeholder="Max" value={max} onChange={e => setMax(e.target.value.replace(/[^\d]/g, ''))} />
            </div>
            <p className="mt-1.5 text-xs text-faint">
              {perPerson && travelers > 1 && max
                ? <>Total for {travelers} people: <strong className="text-ink">{min ? `${money(Number(min) * travelers, currency)} – ` : 'up to '}{money(Number(max) * travelers, currency)}</strong>. </>
                : null}
              Used for the 🎯 Your budget option. Leave empty and we'll suggest a balanced plan.
            </p>
          </div>

          <div>
            <span className="text-sm font-medium">Interests</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {INTEREST_OPTIONS.map(i => {
                const on = interests.includes(i)
                return (
                  <button key={i} type="button" onClick={() => toggle(i)} aria-pressed={on}
                    className={`rounded-full border px-3.5 py-1.5 text-sm transition ${on ? 'border-accent bg-accent text-accent-ink' : 'border-line text-muted hover:border-accent/50 hover:text-ink'}`}>
                    {i}
                  </button>
                )
              })}
            </div>
          </div>

          <label className="block">
            <span className="text-sm font-medium">Anything else? <span className="font-normal text-faint">(optional)</span></span>
            <textarea rows={2} className={`${field} mt-2 resize-none`} value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="e.g. vegetarian, travelling with kids, prefer quiet areas" maxLength={400} />
          </label>

          {error && <p role="alert" className="text-sm text-bad">{error}</p>}
          <button type="submit" className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 font-medium text-accent-ink transition hover:opacity-90">
            Build my 3 options <ArrowRight className="size-4" />
          </button>
        </form>

        <div className="mt-8">
          <div className="flex items-center gap-3 text-xs text-faint"><span className="h-px flex-1 bg-line" /> or just describe it <span className="h-px flex-1 bg-line" /></div>
          <form onSubmit={e => { e.preventDefault(); if (freeform.trim()) go(freeform.trim()) }} className="mt-4 flex gap-2">
            <input className={field} value={freeform} onChange={e => setFreeform(e.target.value)} aria-label="Describe your trip"
              placeholder="A relaxed week in Bali in July, around $1,500 for two, surfing and temples" />
            <button type="submit" disabled={!freeform.trim()} className="shrink-0 rounded-xl bg-ink px-4 text-sm font-medium text-bg disabled:opacity-30">Go</button>
          </form>
        </div>
      </div>
    </div>
  )
}
