export type AgentName = 'supervisor' | 'research' | 'weather' | 'budget' | 'booking' | 'writer'
export type AgentStatus = 'running' | 'done' | 'error' | 'skipped'

export interface AgentEvent {
  type: 'agent'
  agent: AgentName
  status: AgentStatus
  detail: string
  intent?: string
  agents?: AgentName[]
  queries?: string[]
  trip?: Trip
}

export interface Source {
  n: number
  title: string
  source: string
  source_type: 'guide' | 'upload' | 'web' | string
  section: string | null
  page: number | null
  score: number
  text: string
}

export interface Trip {
  destination?: string | null
  country?: string | null
  start_date?: string | null
  days?: number | null
  travelers?: number | null
  budget?: number | null
  currency?: string | null
  style?: string | null
  interests?: string[]
  origin?: string | null
}

export interface DailyWeather {
  date: string
  min_c: number
  max_c: number
  condition: string
  rain_mm: number
}
export interface Weather {
  location: string
  daily: DailyWeather[]
  fetched_at: string
}

export interface FinalEvent {
  answer: string
  sources: Source[]
  trip: Trip
  bookings: string[]
  weather: Weather | null
  intent: string
}

export interface KnowledgeDoc {
  doc_id: string
  source: string
  title: string
  source_type: string
  destination: string | null
  created_at: number
  chunks: number
}

export interface Health {
  ok: boolean
  missing_keys: string[]
  chunks: number
  model: string
}

export interface SearchResult {
  queries: string[]
  destination: string | null
  used_web: boolean
  trace: string[]
  sources: Source[]
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => fetch('/api/health').then(json<Health>),
  documents: () => fetch('/api/documents').then(json<KnowledgeDoc[]>),
  deleteDocument: (id: string) => fetch(`/api/documents/${id}`, { method: 'DELETE' }).then(json),
  upload: (file: File, destination: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('destination', destination)
    return fetch('/api/documents', { method: 'POST', body: form })
      .then(json<{ doc_id: string; chunks: number; filename: string }>)
  },
  search: (query: string, destination: string, allow_web: boolean) =>
    fetch('/api/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ query, destination: destination || null, allow_web }),
    }).then(json<SearchResult>),
}

export interface StreamHandlers {
  onAgent: (e: AgentEvent) => void
  onToken: (text: string) => void
  onFinal: (e: FinalEvent) => void
  onError: (message: string) => void
}

/** POST /api/chat and parse the Server-Sent Events stream. */
export async function streamChat(threadId: string, message: string, h: StreamHandlers, signal: AbortSignal) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify({ thread_id: threadId, message }),
    signal,
  })
  if (!res.ok || !res.body) {
    await json(res) // throws with the server's message
    return
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (!data.length) continue
      const payload = JSON.parse(data.join('\n'))
      if (event === 'agent') h.onAgent(payload)
      else if (event === 'token') h.onToken(payload.text)
      else if (event === 'final') h.onFinal(payload)
      else if (event === 'error') h.onError(payload.message)
    }
  }
}
