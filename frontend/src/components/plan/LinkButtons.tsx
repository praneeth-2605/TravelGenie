import { ExternalLink as ExternalIcon } from 'lucide-react'
import type { ExternalLink } from '../../lib/links'

/** Small "open on …" buttons for booking and map links. */
export function LinkButtons({ links, className = '' }: { links: ExternalLink[]; className?: string }) {
  if (!links.length) return null
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {links.map(l => (
        <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-accent transition hover:border-accent/60 hover:bg-accent-soft/40">
          {l.label} <ExternalIcon className="size-3" />
        </a>
      ))}
    </div>
  )
}
