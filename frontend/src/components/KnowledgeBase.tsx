import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, FileText, Globe, Loader2, Search, Trash2, Upload } from 'lucide-react'
import { api, type KnowledgeDoc, type SearchResult } from '../lib/api'

const ICON = { guide: BookOpen, upload: FileText, web: Globe } as Record<string, typeof Globe>
const ACCEPT = '.pdf,.md,.markdown,.txt,.csv,.json,.html'

export function KnowledgeBase() {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [destination, setDestination] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState('')
  const [qDest, setQDest] = useState('')
  const [allowWeb, setAllowWeb] = useState(false)
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)

  const refresh = useCallback(async () => {
    try {
      setDocs(await api.documents())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const upload = async (files: FileList | File[]) => {
    setUploading(true)
    setNotice(null)
    const done: string[] = []
    try {
      for (const f of Array.from(files)) {
        const r = await api.upload(f, destination.trim())
        done.push(`${r.filename} (${r.chunks} chunks)`)
      }
      setNotice(`Indexed ${done.join(', ')}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
      refresh()
    }
  }

  const remove = async (d: KnowledgeDoc) => {
    if (!confirm(`Remove "${d.title}" from the knowledge base?`)) return
    await api.deleteDocument(d.doc_id).catch(e => setError((e as Error).message))
    refresh()
  }

  const search = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      setResult(await api.search(query.trim(), qDest.trim(), allowWeb))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const counts = docs.reduce<Record<string, number>>((a, d) => ({ ...a, [d.source_type]: (a[d.source_type] ?? 0) + 1 }), {})
  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Knowledge base</h1>
        <p className="mt-2 max-w-2xl text-muted">
          Everything the Research agent can retrieve from: curated guides, web results cached from
          earlier searches, and documents you upload (bookings, visa rules, guidebooks).
          <strong className="font-medium text-ink"> Your uploads are private:</strong> they're only used in your own answers.
        </p>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[['Documents', docs.length], ['Chunks', totalChunks], ['Your uploads', counts.upload ?? 0], ['Cached web', counts.web ?? 0]].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-line bg-surface p-4">
              <div className="text-2xl font-semibold tabular-nums">{v}</div>
              <div className="text-xs text-muted">{k}</div>
            </div>
          ))}
        </div>

        {error && <div className="mt-4 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>}

        {/* Upload */}
        <section className="mt-8">
          <h2 className="text-sm font-semibold">Add documents</h2>
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) upload(e.dataTransfer.files) }}
            className={`mt-2 rounded-2xl border-2 border-dashed p-6 text-center transition ${dragging ? 'border-accent bg-accent-soft/40' : 'border-line bg-surface'}`}
          >
            {uploading ? <Loader2 className="mx-auto size-6 animate-spin text-accent" /> : <Upload className="mx-auto size-6 text-accent" />}
            <p className="mt-2 text-sm">
              Drop files here or{' '}
              <button type="button" onClick={() => fileRef.current?.click()} className="font-medium text-accent hover:underline">browse</button>
            </p>
            <p className="mt-1 text-xs text-faint">PDF, Markdown, text, CSV, JSON or HTML, up to 20MB</p>
            <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden"
              onChange={e => { if (e.target.files?.length) upload(e.target.files); e.target.value = '' }} />
            <div className="mx-auto mt-4 flex max-w-sm items-center gap-2">
              <label htmlFor="kb-dest" className="shrink-0 text-xs text-muted">Destination tag</label>
              <input id="kb-dest" value={destination} onChange={e => setDestination(e.target.value)} placeholder="optional, e.g. Goa"
                className="w-full rounded-lg border border-line bg-bg px-2.5 py-1.5 text-sm focus:border-accent focus:outline-none" />
            </div>
          </div>
          {notice && <p className="mt-2 text-sm text-ok">{notice}</p>}
        </section>

        {/* Retrieval inspector */}
        <section className="mt-10">
          <h2 className="text-sm font-semibold">Retrieval inspector</h2>
          <p className="mt-1 text-sm text-muted">Run the same pipeline the Research agent uses and see each stage.</p>
          <form onSubmit={search} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. which day is the Louvre closed?"
              aria-label="Search query"
              className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none" />
            <input value={qDest} onChange={e => setQDest(e.target.value)} placeholder="destination" aria-label="Destination filter"
              className="rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none sm:w-36" />
            <label className="flex items-center gap-1.5 text-sm text-muted">
              <input type="checkbox" checked={allowWeb} onChange={e => setAllowWeb(e.target.checked)} className="accent-[var(--accent)]" />
              web fallback
            </label>
            <button type="submit" disabled={searching}
              className="flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50">
              {searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />} Search
            </button>
          </form>
          {result && (
            <div className="mt-4 rounded-xl border border-line bg-surface p-4">
              <ol className="space-y-1 font-mono text-xs text-muted">
                {result.trace.map((t, i) => <li key={i}><span className="text-accent">{i + 1}.</span> {t}</li>)}
                {result.used_web && <li><span className="text-accent">↳</span> web results cached into the vector DB</li>}
              </ol>
              <ul className="mt-4 space-y-3">
                {result.sources.length === 0 && <li className="text-sm text-muted">Nothing relevant enough passed the reranker.</li>}
                {result.sources.map(s => (
                  <li key={s.n} className="border-t border-line pt-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-accent">[{s.n}]</span>
                      <span className="font-medium">{s.title}</span>
                      {s.section && <span className="truncate text-xs text-faint">{s.section}</span>}
                      <span className="ml-auto font-mono text-xs text-faint">rerank {s.score.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 line-clamp-4 text-xs leading-relaxed text-muted">{s.text}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Documents */}
        <section className="mt-10">
          <h2 className="text-sm font-semibold">Indexed documents</h2>
          {loading ? (
            <Loader2 className="mt-4 size-5 animate-spin text-faint" />
          ) : (
            <div className="mt-2 overflow-hidden rounded-xl border border-line">
              <table className="w-full text-sm">
                <thead className="bg-surface-2 text-left text-xs text-muted">
                  <tr><th className="px-3 py-2 font-medium">Document</th><th className="hidden px-3 py-2 font-medium sm:table-cell">Destination</th><th className="px-3 py-2 text-right font-medium">Chunks</th><th className="w-10" /></tr>
                </thead>
                <tbody>
                  {docs.map(d => {
                    const Icon = ICON[d.source_type] ?? FileText
                    return (
                      <tr key={d.doc_id} className="border-t border-line bg-surface">
                        <td className="max-w-0 px-3 py-2">
                          <div className="flex items-center gap-2">
                            <Icon className="size-4 shrink-0 text-muted" />
                            <span className="truncate" title={d.source}>{d.title}</span>
                            <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted uppercase">{d.source_type}</span>
                            {d.mine && <span className="shrink-0 rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent">Private · only you</span>}
                          </div>
                        </td>
                        <td className="hidden px-3 py-2 capitalize text-muted sm:table-cell">{d.destination ?? '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted">{d.chunks}</td>
                        <td className="px-2 py-2">
                          {d.mine && (
                            <button type="button" onClick={() => remove(d)} aria-label={`Delete ${d.title}`} className="rounded p-1 text-faint hover:text-bad">
                              <Trash2 className="size-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
