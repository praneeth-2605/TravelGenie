import type { AgentEvent, Source, Trip, Weather } from './api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  steps?: AgentEvent[]
  sources?: Source[]
  error?: string
  streaming?: boolean
}

export interface Thread {
  id: string
  title: string
  updatedAt: number
  messages: ChatMessage[]
  trip?: Trip
  weather?: Weather | null
  bookings?: string[]
}

const KEY = 'travelgenie.threads.v1'

export const uid = () =>
  (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/-/g, '').slice(0, 20)

export function loadThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(KEY)
    const list: Thread[] = raw ? JSON.parse(raw) : []
    // A reload mid-stream leaves messages flagged as streaming; clear that.
    return list.map(t => ({ ...t, messages: t.messages.map(m => ({ ...m, streaming: false })) }))
  } catch {
    return []
  }
}

export function saveThreads(threads: Thread[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(threads.slice(0, 50)))
  } catch { /* storage full or blocked */ }
}

export function titleFrom(text: string) {
  const t = text.replace(/\s+/g, ' ').trim()
  return t.length > 48 ? `${t.slice(0, 46)}…` : t || 'New trip'
}
