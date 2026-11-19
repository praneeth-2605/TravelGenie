import { useState } from 'react'
import { AlertTriangle, Check, Copy, Sparkles } from 'lucide-react'
import type { ChatMessage } from '../lib/threads'
import { AgentTrace } from './AgentTrace'
import { Markdown } from './Markdown'

interface Props {
  message: ChatMessage
  onCite: (n: number) => void
}

export function Message({ message: m, onCite }: Props) {
  const [copied, setCopied] = useState(false)

  if (m.role === 'user') {
    return (
      <div className="rise flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
          {m.content}
        </div>
      </div>
    )
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(m.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked */ }
  }

  return (
    <div className="rise flex gap-3">
      <div className="mt-1 grid size-7 shrink-0 place-items-center rounded-lg bg-accent text-accent-ink">
        <Sparkles className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        {m.steps && <AgentTrace steps={m.steps} live={!!m.streaming} />}
        {m.content ? (
          <Markdown text={m.content} sources={m.sources} streaming={m.streaming} onCite={onCite} />
        ) : m.streaming ? (
          <div className="flex gap-1 py-2" aria-label="Thinking">
            {[0, 1, 2].map(i => (
              <span key={i} className="size-1.5 animate-bounce rounded-full bg-faint" style={{ animationDelay: `${i * 120}ms` }} />
            ))}
          </div>
        ) : null}
        {m.error && (
          <div className="mt-2 flex items-start gap-2 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{m.error}</span>
          </div>
        )}
        {!m.streaming && m.content && (
          <div className="mt-2 flex items-center gap-3 text-xs text-faint">
            <button type="button" onClick={copy} className="flex items-center gap-1 hover:text-ink">
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            {!!m.sources?.length && <span>{m.sources.length} sources</span>}
          </div>
        )}
      </div>
    </div>
  )
}
