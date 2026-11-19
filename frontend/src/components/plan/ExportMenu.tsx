import { useEffect, useRef, useState } from 'react'
import { CalendarPlus, ChevronDown, Download, FileText, FileType2 } from 'lucide-react'
import { api, TIER_META, type Tier } from '../../lib/api'

export function ExportMenu({ tripId, selected }: { tripId: string; selected: Tier }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [open])

  const items = [
    { href: api.exportUrl(tripId, 'pdf', selected), icon: FileType2, label: `PDF · ${TIER_META[selected].label} option`, hint: 'Printable plan' },
    { href: api.exportUrl(tripId, 'pdf'), icon: FileType2, label: 'PDF · all 3 options', hint: 'Compare side by side' },
    { href: api.exportUrl(tripId, 'ics'), icon: CalendarPlus, label: 'Calendar (.ics)', hint: 'Google, Apple, Outlook' },
    { href: api.exportUrl(tripId, 'md'), icon: FileText, label: 'Markdown (.md)', hint: 'Notes apps, docs' },
  ]

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} aria-haspopup="menu"
        className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:border-accent/50">
        <Download className="size-4" /> Export <ChevronDown className={`size-3.5 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-[500] mt-1.5 w-64 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl">
          {items.map(it => (
            <a key={it.href} role="menuitem" href={it.href} download onClick={() => setOpen(false)}
              className="flex items-start gap-3 px-3.5 py-2.5 hover:bg-surface-2">
              <it.icon className="mt-0.5 size-4 text-accent" />
              <span>
                <span className="block text-sm font-medium">{it.label}</span>
                <span className="block text-xs text-muted">{it.hint}</span>
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
