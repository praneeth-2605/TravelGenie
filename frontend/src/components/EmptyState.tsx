import { CloudSun, Search, Ticket, Wallet } from 'lucide-react'

const SUGGESTIONS = [
  { title: '4 days in Goa', body: 'Mid-December, ₹40,000 for two, beaches and seafood, not too much partying', },
  { title: 'Tokyo for first-timers', body: '6 days in early April, food and temples, is the JR Pass worth it?', },
  { title: 'Paris on a budget', body: 'A long weekend in May under €900, art museums and bakeries', },
  { title: 'Bali, slow travel', body: '10 days in July split between Ubud and Uluwatu, yoga and surf', },
]

const TEAM = [
  { icon: Search, label: 'Research', body: 'Hybrid RAG over guides, your docs and the web' },
  { icon: CloudSun, label: 'Weather', body: 'Live 5-day forecast' },
  { icon: Wallet, label: 'Budget', body: 'Cost breakdown and savings' },
  { icon: Ticket, label: 'Booking', body: 'Simulated reservations' },
]

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-[10vh] pb-8">
      <p className="rise text-sm font-medium tracking-[0.18em] text-accent uppercase">TravelGenie</p>
      <h1 className="rise mt-3 font-serif text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
        Where are we going next?
      </h1>
      <p className="rise mt-3 max-w-xl text-muted">
        A team of AI agents researches, budgets and checks the weather, then writes one plan
        with every fact linked to its source.
      </p>

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((s, i) => (
          <button
            key={s.title}
            type="button"
            onClick={() => onPick(`${s.title}: ${s.body}`)}
            style={{ animationDelay: `${80 + i * 50}ms` }}
            className="rise group rounded-xl border border-line bg-surface p-4 text-left transition hover:-translate-y-0.5 hover:border-accent/50"
          >
            <div className="font-medium group-hover:text-accent">{s.title}</div>
            <div className="mt-1 text-sm text-muted">{s.body}</div>
          </button>
        ))}
      </div>

      <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line pt-6 sm:grid-cols-4">
        {TEAM.map(t => (
          <div key={t.label} className="flex gap-2.5">
            <t.icon className="mt-0.5 size-4 shrink-0 text-accent" />
            <div>
              <div className="text-sm font-medium">{t.label}</div>
              <div className="text-xs text-muted">{t.body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
