// ---------------------------------------------------------------- types
export type AgentName = 'supervisor' | 'research' | 'weather' | 'stays' | 'sights' | 'transport' | 'web' | 'booking' | 'planner' | 'writer'
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
  source_type: string
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
  budget_min?: number | null
  budget_max?: number | null
  currency?: string | null
  style?: string | null
  interests?: string[] | null
  origin?: string | null
}

export type TransportModeName = 'flight' | 'train' | 'bus' | 'car' | 'ferry'

export interface TransportMode {
  mode: TransportModeName
  label: string | null
  available: boolean
  duration: string | null
  price_min: number | null
  price_max: number | null
  frequency: string | null
  route: string | null
  book_via: string[]
  pros: string | null
  cons: string | null
  best_for: string | null
}

export interface Transport {
  summary: string
  modes: TransportMode[]
  recommendation: string | null
  origin: string
  destination: string
  distance_km: number | null
  currency: string
  guide_url: string | null
}

export interface WebResult {
  title: string
  url: string
  snippet: string
  source: 'web' | 'wikivoyage' | string
}

export interface OptionDetails {
  overview: string
  days: {
    day: number
    summary: string
    meals: { meal: string; place: string; try: string | null; cost: number | null }[]
    getting_around: string | null
    spend: number | null
    tip: string | null
  }[]
  booking_checklist: { item: string; when: string; where: string; cost: number | null }[]
  money_tips: string[]
  good_to_know: string[]
}

export interface Place {
  id: string
  name: string
  kind?: string
  tier?: 'budget' | 'mid' | 'luxury'
  area?: string
  lat?: number
  lon?: number
  price?: string
  hours?: string
  url?: string
  description?: string
}

export interface PlanItem {
  time: string
  title: string
  description: string
  place_id: string | null
  place?: Place
  cost: number | null
  cite: number[] | null
}

export interface PlanDay {
  day: number
  date: string | null
  title: string
  area: string | null
  items: PlanItem[]
}

export type Tier = 'budget' | 'luxury' | 'yours'

export interface PlanOption {
  tier: Tier
  label: string
  title: string
  total: number
  per_person: number | null
  per_day: number | null
  breakdown: { travel?: number; stay: number; food: number; transport: number; activities: number; other: number }
  getting_there: { mode: string; detail: string; duration: string | null; cost: number | null } | null
  details?: OptionDetails
  stay: { place_id: string | null; name: string; nightly: number | null; why: string; place?: Place }
  alt_stays: Place[]
  highlights: string[]
  fits_budget: boolean | null
  note: string | null
}

export interface Marker extends Place {
  kind: string
  days?: number[]
  tiers?: Tier[]
}

export interface DailyWeather { date: string; min_c: number; max_c: number; condition: string; rain_mm: number }
export interface Weather { location: string; daily: DailyWeather[]; fetched_at: string }

export interface TripPlan {
  summary: string
  answer: string | null
  assumptions: string[]
  currency: string
  days: PlanDay[]
  options: PlanOption[]
  packing: string[]
  weather_note: string | null
  tips: string[]
  trip: Trip
  travelers: number
  sources: Source[]
  map_center: { lat: number; lon: number; name: string } | null
  markers: Marker[]
  weather: Weather | null
  stay_candidates: Place[]
  transport: Transport | null
  web_results: WebResult[]
  selected_tier: Tier | null
}

export interface User {
  id: string
  email: string
  name: string
  avatar_url: string | null
  has_password: boolean
  google_linked: boolean
  created_at: number
}

export interface Settings {
  home_currency: string
  travel_style: 'budget' | 'balanced' | 'luxury'
  default_travelers: number
  budget_min: number | null
  budget_max: number | null
  interests: string[]
  dietary: string
  pace: 'relaxed' | 'moderate' | 'packed'
  theme: 'system' | 'light' | 'dark'
  home_city: string
}

export interface TripSummary {
  id: string
  title: string
  destination: string | null
  start_date: string | null
  days: number | null
  favorite: boolean
  created_at: number
  updated_at: number
  summary: string | null
  currency: string | null
  options: { tier: Tier; label: string; total: number; stay: string }[]
  map_center: { lat: number; lon: number } | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  steps?: AgentEvent[]
  sources?: Source[]
  hasPlan?: boolean
  error?: string
  streaming?: boolean
}

export interface TripDetail extends Omit<TripSummary, 'options' | 'summary' | 'map_center'> {
  plan: TripPlan | null
  messages: { role: 'user' | 'assistant'; content: string }[]
  brief: Trip
  bookings: string[]
  sources: Source[]
}

export interface FinalEvent {
  answer: string
  intent: string
  plan: TripPlan | null
  sources: Source[]
  trip: Trip
  bookings: string[]
  weather: Weather | null
}

export interface KnowledgeDoc {
  doc_id: string
  source: string
  title: string
  source_type: string
  destination: string | null
  created_at: number
  chunks: number
  mine: boolean
}

export interface Health { ok: boolean; missing_keys: string[]; chunks: number; model: string; google_login: boolean }

export interface SearchResult {
  queries: string[]
  destination: string | null
  used_web: boolean
  trace: string[]
  sources: Source[]
}

// ---------------------------------------------------------------- http
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: 'same-origin', ...init })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) {
        msg = typeof body.detail === 'string'
          ? body.detail
          : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('; ') : JSON.stringify(body.detail)
      }
    } catch { /* not JSON */ }
    if (res.status === 401 && !url.startsWith('/api/auth/')) onUnauthorized?.()
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/api/health'),
  authConfig: () => request<{ google_client_id: string | null }>('/api/auth/config'),
  me: () => request<{ user: User; settings: Settings }>('/api/auth/me'),
  signup: (name: string, email: string, password: string) =>
    request<{ user: User; settings: Settings }>('/api/auth/signup', json('POST', { name, email, password })),
  login: (email: string, password: string) =>
    request<{ user: User; settings: Settings }>('/api/auth/login', json('POST', { email, password })),
  google: (credential: string) =>
    request<{ user: User; settings: Settings }>('/api/auth/google', json('POST', { credential })),
  logout: () => request('/api/auth/logout', json('POST')),
  logoutAll: () => request('/api/auth/logout-all', json('POST')),
  updateProfile: (name: string) => request<{ user: User; settings: Settings }>('/api/account/profile', json('PUT', { name })),
  changePassword: (current_password: string | null, new_password: string) =>
    request('/api/account/password', json('PUT', { current_password, new_password })),
  deleteAccount: () => request('/api/account', json('DELETE', { confirm: 'DELETE' })),
  updateSettings: (s: Partial<Settings>) => request<Settings>('/api/settings', json('PUT', s)),

  trips: () => request<TripSummary[]>('/api/trips'),
  trip: (id: string) => request<TripDetail>(`/api/trips/${id}`),
  patchTrip: (id: string, body: { title?: string; favorite?: boolean }) => request(`/api/trips/${id}`, json('PATCH', body)),
  deleteTrip: (id: string) => request(`/api/trips/${id}`, json('DELETE')),
  selectOption: (id: string, tier: Tier) =>
    request<{ plan: TripPlan; message: string }>(`/api/trips/${id}/select`, json('POST', { tier })),
  exportUrl: (id: string, format: 'pdf' | 'ics' | 'md', option?: Tier) =>
    `/api/trips/${id}/export?format=${format}${option ? `&option=${option}` : ''}`,

  documents: () => request<KnowledgeDoc[]>('/api/documents'),
  deleteDocument: (id: string) => request(`/api/documents/${id}`, json('DELETE')),
  upload: (file: File, destination: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('destination', destination)
    return request<{ doc_id: string; chunks: number; filename: string }>('/api/documents', { method: 'POST', body: form })
  },
  search: (query: string, destination: string, allow_web: boolean) =>
    request<SearchResult>('/api/search', json('POST', { query, destination: destination || null, allow_web })),
}

// ---------------------------------------------------------------- streaming chat
export interface StreamHandlers {
  onAgent: (e: AgentEvent) => void
  onToken: (text: string) => void
  onFinal: (e: FinalEvent) => void
  onError: (message: string) => void
}

export async function streamChat(tripId: string, message: string, h: StreamHandlers, signal: AbortSignal) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify({ trip_id: tripId, message }),
    signal,
  })
  if (!res.ok || !res.body) {
    let msg = `${res.status} ${res.statusText}`
    try { msg = (await res.json()).detail ?? msg } catch { /* ignore */ }
    if (res.status === 401) onUnauthorized?.()
    throw new ApiError(res.status, msg)
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

// ---------------------------------------------------------------- helpers
export const uid = () =>
  (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/-/g, '').slice(0, 24)

export function money(value: number | null | undefined, currency: string | null | undefined) {
  if (value == null) return '—'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD', maximumFractionDigits: 0 }).format(value)
  } catch {
    return `${currency ?? ''} ${Math.round(value).toLocaleString()}`.trim()
  }
}

export const TIER_META: Record<Tier, { emoji: string; label: string; blurb: string; planName: string }> = {
  budget: { emoji: '💰', label: 'Budget', blurb: 'Cheapest sensible trip', planName: 'Budget plan' },
  luxury: { emoji: '💎', label: 'Luxury', blurb: 'Premium comfort', planName: 'Luxury plan' },
  yours: { emoji: '🎯', label: 'Your budget', blurb: 'Fitted to your range', planName: 'budget-matched plan' },
}
