import { BookOpen, ExternalLink, Globe } from 'lucide-react'
import type { Source, TripPlan } from '../../lib/api'
import { Sources } from './Sources'

export function WebPanel({ plan, sources, active }: { plan: TripPlan; sources: Source[]; active: number | null }) {
  const web = plan.web_results ?? []
  const viaGuide = web.length > 0 && web.every(w => w.source === 'wikivoyage')
  return (
    <div className="space-y-8">
      <section>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Globe className="size-5 text-accent" /> From the web</h2>
        <p className="mt-0.5 text-sm text-muted">
          {viaGuide ? 'Practical notes from the live Wikivoyage guide for this destination.' : 'Fresh results found for this trip.'}
        </p>
        {web.length === 0 ? (
          <p className="mt-3 rounded-2xl border border-line bg-surface p-5 text-sm text-muted">No web results for this destination.</p>
        ) : (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {web.map((r, i) => {
              let host = ''
              try { host = new URL(r.url).hostname.replace(/^www\./, '') } catch { /* ignore */ }
              return (
                <a key={i} href={r.url} target="_blank" rel="noreferrer"
                  className="group rounded-2xl border border-line bg-surface p-4 transition hover:border-accent/50">
                  <div className="flex items-center gap-1.5 text-xs text-faint">
                    {r.source === 'wikivoyage' ? <BookOpen className="size-3" /> : <Globe className="size-3" />} {host}
                  </div>
                  <h3 className="mt-1 flex items-start gap-1 font-medium group-hover:text-accent">
                    {r.title} <ExternalLink className="mt-1 size-3 shrink-0 opacity-0 group-hover:opacity-100" />
                  </h3>
                  <p className="mt-1.5 line-clamp-4 text-sm leading-relaxed text-muted">{r.snippet}</p>
                </a>
              )
            })}
          </div>
        )}
      </section>
      <section>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><BookOpen className="size-5 text-accent" /> Knowledge base sources</h2>
        <p className="mb-3 mt-0.5 text-sm text-muted">Passages the Research agent used. Numbers match the citations in the itinerary.</p>
        <Sources sources={sources} active={active} />
      </section>
    </div>
  )
}
