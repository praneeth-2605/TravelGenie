import { useEffect, useRef } from 'react'
import { BookOpen, FileText, Globe } from 'lucide-react'
import type { Source } from '../../lib/api'

const ICON = { guide: BookOpen, upload: FileText, web: Globe } as Record<string, typeof Globe>

export function Sources({ sources, active }: { sources: Source[]; active: number | null }) {
  const refs = useRef(new Map<number, HTMLLIElement>())
  useEffect(() => {
    if (active != null) refs.current.get(active)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [active])

  if (!sources.length) {
    return <p className="rounded-2xl border border-line bg-surface p-6 text-muted">No guide sources were used for this plan. Stays and sights come from Wikivoyage.</p>
  }
  return (
    <ol className="space-y-3">
      {sources.map(s => {
        const Icon = ICON[s.source_type] ?? FileText
        const isUrl = s.source.startsWith('http')
        return (
          <li key={s.n} ref={el => { if (el) refs.current.set(s.n, el); else refs.current.delete(s.n) }}
            className={`rounded-2xl border bg-surface p-4 transition ${active === s.n ? 'border-accent bg-accent-soft/30' : 'border-line'}`}>
            <div className="flex items-start gap-2.5">
              <span className="grid size-6 shrink-0 place-items-center rounded-md bg-accent-soft font-mono text-xs text-accent">{s.n}</span>
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {isUrl ? <a href={s.source} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">{s.title}</a> : s.title}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-faint">
                  <Icon className="size-3" /> <span className="capitalize">{s.source_type}</span>
                  {s.section && <span className="truncate">· {s.section}</span>}
                  {s.page && <span>· p.{s.page}</span>}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{s.text.replace(/\*\*|__|^#+\s*/gm, '')}</p>
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
