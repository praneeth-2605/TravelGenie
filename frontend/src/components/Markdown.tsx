import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Source } from '../lib/api'

/** Turn bare [n] markers (not markdown links) into #cite-n links we can render as chips. */
function linkCitations(text: string) {
  return text
    // gpt-oss native style while streaming: 【3†L1-L4】 → [3]; non-numeric markers dropped
    .replace(/【\s*([^】†]*?)\s*(?:†[^】]*)?】/g, (_, ref: string) => (/^\d+$/.test(ref) ? `[${ref}]` : ''))
    .replace(/\[(\d{1,2})\](?![(:])/g, '[$1](#cite-$1)')
}

interface Props {
  text: string
  sources?: Source[]
  streaming?: boolean
  onCite?: (n: number) => void
}

function MarkdownImpl({ text, sources = [], streaming, onCite }: Props) {
  const known = new Set(sources.map(s => s.n))
  return (
    <div className={`answer prose prose-sm sm:prose-base max-w-none prose-p:leading-relaxed prose-li:my-0.5 ${streaming ? 'caret' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const m = href?.match(/^#cite-(\d+)$/)
            if (m) {
              const n = Number(m[1])
              const src = sources.find(s => s.n === n)
              if (!known.has(n)) return <sup className="text-faint">[{n}]</sup>
              return (
                <button
                  type="button"
                  onClick={() => onCite?.(n)}
                  title={src ? `${src.title}${src.section ? ` — ${src.section}` : ''}` : undefined}
                  className="mx-0.5 inline-flex h-[1.35em] min-w-[1.35em] -translate-y-px items-center justify-center rounded-md bg-accent-soft px-1 align-middle font-mono text-[0.7em] font-medium text-accent no-underline transition hover:bg-accent hover:text-accent-ink"
                >
                  {n}
                </button>
              )
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>
          },
          h2({ children }) {
            const label = String(Array.isArray(children) ? children.join('') : children ?? '')
            const day = label.match(/^Day\s+(\d+)\s*[—–-]?\s*(.*)$/i)
            if (day) {
              return (
                <h2 className="!mt-8 flex items-baseline gap-3 border-t border-line pt-6">
                  <span className="rounded-full bg-accent px-2.5 py-0.5 font-sans text-xs font-semibold tracking-wide text-accent-ink uppercase">
                    Day {day[1]}
                  </span>
                  <span>{day[2]}</span>
                </h2>
              )
            }
            return <h2>{children}</h2>
          },
          table({ children }) {
            return <div className="overflow-x-auto"><table>{children}</table></div>
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  )
}

export const Markdown = memo(MarkdownImpl)
