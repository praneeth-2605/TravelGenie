import { Database, MessageSquare, Moon, PanelLeftClose, Plus, Sun, Trash2 } from 'lucide-react'
import type { Thread } from '../lib/threads'

interface Props {
  threads: Thread[]
  activeId: string | null
  view: 'chat' | 'knowledge'
  theme: 'light' | 'dark'
  onNew: () => void
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onKnowledge: () => void
  onToggleTheme: () => void
  onCollapse: () => void
}

function group(ts: number) {
  const days = (Date.now() - ts) / 86_400_000
  if (days < 1) return 'Today'
  if (days < 7) return 'Previous 7 days'
  return 'Older'
}

export function Sidebar(p: Props) {
  const groups = new Map<string, Thread[]>()
  for (const t of [...p.threads].sort((a, b) => b.updatedAt - a.updatedAt)) {
    const g = group(t.updatedAt)
    groups.set(g, [...(groups.get(g) ?? []), t])
  }

  return (
    <nav className="flex h-full w-full flex-col bg-sidebar" aria-label="Conversations">
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <div className="flex items-center gap-2 px-1.5">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="font-serif text-lg font-semibold tracking-tight">TravelGenie</span>
        </div>
        <button type="button" onClick={p.onCollapse} aria-label="Hide sidebar" className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
          <PanelLeftClose className="size-4" />
        </button>
      </div>

      <div className="space-y-0.5 px-2">
        <button type="button" onClick={p.onNew}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-accent hover:bg-surface-2">
          <Plus className="size-4" /> New trip
        </button>
        <button type="button" onClick={p.onKnowledge}
          className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm hover:bg-surface-2 ${p.view === 'knowledge' ? 'bg-surface-2 font-medium' : 'text-muted'}`}>
          <Database className="size-4" /> Knowledge base
        </button>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto px-2 pb-2">
        {p.threads.length === 0 && <p className="px-2.5 py-2 text-xs text-faint">Your trips will show up here.</p>}
        {[...groups].map(([label, items]) => (
          <div key={label} className="mb-3">
            <div className="px-2.5 pb-1 text-[11px] font-medium text-faint">{label}</div>
            {items.map(t => {
              const active = p.view === 'chat' && t.id === p.activeId
              return (
                <div key={t.id} className={`group flex items-center rounded-lg ${active ? 'bg-surface-2' : 'hover:bg-surface-2/70'}`}>
                  <button type="button" onClick={() => p.onSelect(t.id)}
                    className={`flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-1.5 text-left text-sm ${active ? 'text-ink' : 'text-muted'}`}>
                    <MessageSquare className="size-3.5 shrink-0 opacity-60" />
                    <span className="truncate">{t.title}</span>
                  </button>
                  <button type="button" onClick={() => p.onDelete(t.id)} aria-label={`Delete ${t.title}`}
                    className="mr-1 rounded p-1 text-faint opacity-0 group-hover:opacity-100 hover:text-bad focus:opacity-100">
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      <div className="border-t border-line p-2">
        <button type="button" onClick={p.onToggleTheme}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-ink">
          {p.theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {p.theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </div>
    </nav>
  )
}
