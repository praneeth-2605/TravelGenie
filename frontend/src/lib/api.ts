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
  booking_checklist: { item: string; when: string; where: string; cost: number | null }[]
  money_tips: string[]
  good_to_know: string[]
}

export interface Photo {
  url: string
  thumb: string
  page: string
  credit: string
  /** "place" = a photo of this exact place; "area" = taken nearby */
  kind: 'place' | 'area'
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
  photo?: Photo | null
}

export interface PlanStop {
  kind: 'sight' | 'meal' | 'activity' | 'free'
  place_id: string | null
  title: string
  duration_min: number | null
  note: string
  cost: number | null
  cite: number[] | null
  unverified?: boolean
}

export interface PlanDay {
  day: number
  title: string
  area: string | null
  stops: PlanStop[]
}

export type StepKind = 'arrive' | 'hotel' | 'start' | 'sight' | 'meal' | 'activity' | 'free' | 'travel' | 'end' | 'depart'

export interface Step {
  time: string
  end: string | null
  kind: StepKind
  title: string
  detail?: string | null
  minutes?: number | null
  place?: Place
  distance_km?: number
  mode?: string
  estimated?: boolean
  cite?: number[]
  unverified?: boolean
}

export interface ScheduleDay {
  day: number
  date: string | null
  title: string
  area: string | null
  steps: Step[]
}

export type Tier = 'budget' | 'luxury' | 'yours'

export interface GettingThereInfo {
  mode: string
  detail: string
  duration: string | null
  cost: number | null
  arrive_at?: string | null
  depart_from_destination?: string | null
  arrive_time?: string | null
}

export interface StayAdvice {
  area: string
  kind: string
  nightly_min: number | null
  nightly_max: number | null
  why: string
  candidate_ids: string[]
  candidates: Place[]
}

export interface PlanOption {
  tier: Tier
  label: string
  title: string
  total: number
  per_person: number | null
  per_day: number | null
  breakdown: { travel?: number; stay: number; food: number; transport: number; activities: number; other: number }
  getting_there: GettingThereInfo | null
  details?: OptionDetails
  stay: StayAdvice
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
  places: Record<string, Place>
  schedules: Partial<Record<Tier, ScheduleDay[]>>
  hotels: Partial<Record<Tier, string | null>>
  pace?: string
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
  share_token: string | null
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

export interface Health { ok: boolean; missing_keys: string[]; chunks: number; model: string; google_login: boolean; skills?: string[] }

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
  authConfig: () => request<{ google_client_id: string | null; contact_email: string | null }>('/api/auth/config'),
  me: () => request<{ user: User; settings: Settings }>('/api/auth/me'),
  signup: (name: string, email: string, password: string, accept_terms: boolean) =>
    request<{ user: User; settings: Settings }>('/api/auth/signup', json('POST', { name, email, password, accept_terms })),
  login: (email: string, password: string) =>
    request<{ user: User; settings: Settings }>('/api/auth/login', json('POST', { email, password })),
  google: (credential: string) =>
    request<{ user: User; settings: Settings }>('/api/auth/google', json('POST', { credential })),
  logout: () => request('/api/auth/logout', json('POST')),
  logoutAll: () => request('/api/auth/logout-all', json('POST')),
  updateProfile: (name: string) => request<{ user: User; settings: Settings }>('/api/account/profile', json('PUT', { name })),
  changePassword: (current_password: string | null, new_password: string) =>
    request('/api/account/password', json('PUT', { current_password, new_password })),
  accountExportUrl: '/api/account/export',
  deleteAccount: () => request('/api/account', json('DELETE', { confirm: 'DELETE' })),
  updateSettings: (s: Partial<Settings>) => request<Settings>('/api/settings', json('PUT', s)),

  trips: () => request<TripSummary[]>('/api/trips'),
  trip: (id: string) => request<TripDetail>(`/api/trips/${id}`),
  patchTrip: (id: string, body: { title?: string; favorite?: boolean }) => request(`/api/trips/${id}`, json('PATCH', body)),
  deleteTrip: (id: string) => request(`/api/trips/${id}`, json('DELETE')),
  usage: () => request<{ used: number; limit: number; remaining: number | null }>('/api/usage'),
  shareTrip: (id: string) => request<{ token: string }>(`/api/trips/${id}/share`, json('POST')),
  unshareTrip: (id: string) => request(`/api/trips/${id}/share`, json('DELETE')),
  publicTrip: (token: string) =>
    request<{ title: string; destination: string | null; days: number | null; start_date: string | null; plan: TripPlan }>(
      `/api/public/trips/${encodeURIComponent(token)}`),
  selectOption: (id: string, tier: Tier) =>
    request<{ plan: TripPlan; message: string }>(`/api/trips/${id}/select`, json('POST', { tier })),
  exportUrl: (id: string, format: 'pdf' | 'ics' | 'md', option?: Tier) =>
    `/api/trips/${id}/export?format=${format}${option ? `&option=${option}` : ''}`,

  chooseHotel: (id: string, tier: Tier, place_id: string | null) =>
    request<{ plan: TripPlan }>(`/api/trips/${id}/hotel`, json('POST', { tier, place_id })),
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
    // Rupees use Indian grouping (₹1,50,000); other currencies follow the browser's locale.
    const locale = (currency || '').toUpperCase() === 'INR' ? 'en-IN' : undefined
    return new Intl.NumberFormat(locale, { style: 'currency', currency: currency || 'USD', maximumFractionDigits: 0 }).format(value)
  } catch {
    return `${currency ?? ''} ${Math.round(value).toLocaleString()}`.trim()
  }
}

export const TIER_META: Record<Tier, { emoji: string; label: string; blurb: string; planName: string }> = {
  budget: { emoji: '💰', label: 'Budget', blurb: 'Cheapest sensible trip', planName: 'Budget plan' },
  luxury: { emoji: '💎', label: 'Luxury', blurb: 'Premium comfort', planName: 'Luxury plan' },
  yours: { emoji: '🎯', label: 'Your budget', blurb: 'Fitted to your range', planName: 'budget-matched plan' },
}

// ---------------------------------------------------------------- plan helpers
/** The option the itinerary follows: the one the traveller chose, else their own budget. */
export const activeTier = (plan: TripPlan): Tier => plan.selected_tier ?? 'yours'

/** The hotel the traveller picked for an option (or null while they haven't chosen). */
export const pickedHotel = (plan: TripPlan, tier: Tier): Place | null => {
  const id = plan.hotels?.[tier]
  return (id && plan.places?.[id]) || null
}

export function stayLabel(plan: TripPlan, o: PlanOption): string {
  const hotel = pickedHotel(plan, o.tier)
  if (hotel) return hotel.name
  const s = o.stay
  return s ? `${s.kind.charAt(0).toUpperCase()}${s.kind.slice(1)} in ${s.area}` : 'Stay'
}

export function nightlyRange(o: PlanOption, currency: string): string | null {
  const { nightly_min: lo, nightly_max: hi } = o.stay ?? {}
  if (lo == null && hi == null) return null
  if (lo != null && hi != null && lo !== hi) return `${money(lo, currency)}–${money(hi, currency)} / night`
  return `${money(lo ?? hi, currency)} / night`
}

/** Plans made before timestamped schedules existed can't be shown in the new views. */
export const isLegacyPlan = (plan: TripPlan) => !plan.schedules

/** First day of the trip (YYYY-MM-DD), if known. */
export const tripStart = (plan: TripPlan): string | null =>
  plan.trip?.start_date ?? plan.schedules?.yours?.[0]?.date ?? null
