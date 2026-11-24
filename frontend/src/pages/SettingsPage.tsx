import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, Download, Loader2, Monitor, Moon, Sun, X } from 'lucide-react'
import { api, type Settings } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Avatar } from '../components/AppShell'

const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'SGD', 'AED', 'THB', 'IDR']
const field = 'w-full rounded-xl border border-line bg-bg px-3.5 py-2.5 text-[15px] focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none'

function Card({ title, desc, children, danger }: { title: string; desc?: string; children: ReactNode; danger?: boolean }) {
  return (
    <section className={`rounded-2xl border bg-surface p-5 sm:p-6 ${danger ? 'border-bad/40' : 'border-line'}`}>
      <h2 className={`text-lg font-semibold ${danger ? 'text-bad' : ''}`}>{title}</h2>
      {desc && <p className="mt-0.5 text-sm text-muted">{desc}</p>}
      <div className="mt-5">{children}</div>
    </section>
  )
}

function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string; icon?: typeof Sun }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-bg p-1">
      {options.map(o => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${value === o.value ? 'bg-surface font-medium shadow-sm' : 'text-muted hover:text-ink'}`}>
          {o.icon && <o.icon className="size-4" />} {o.label}
        </button>
      ))}
    </div>
  )
}

function Status({ state }: { state: 'idle' | 'saving' | 'saved' | string }) {
  if (state === 'idle') return null
  if (state === 'saving') return <span className="flex items-center gap-1 text-sm text-muted"><Loader2 className="size-4 animate-spin" /> Saving</span>
  if (state === 'saved') return <span className="flex items-center gap-1 text-sm text-ok"><Check className="size-4" /> Saved</span>
  return <span role="alert" className="text-sm text-bad">{state}</span>
}

export function SettingsPage() {
  const { user, settings, setSession, setSettings, logout } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState(user?.name ?? '')
  const [profileState, setProfileState] = useState('idle')
  const [prefs, setPrefs] = useState<Settings>(settings!)
  const [interest, setInterest] = useState('')
  const [prefsState, setPrefsState] = useState('idle')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [pwState, setPwState] = useState('idle')
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)

  if (!user || !settings) return null

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setProfileState('saving')
    try { setSession(await api.updateProfile(name)); setProfileState('saved') } catch (err) { setProfileState((err as Error).message) }
  }

  const savePrefs = async (patch?: Partial<Settings>) => {
    const body = { ...prefs, ...patch }
    setPrefsState('saving')
    try {
      const saved = await api.updateSettings({
        ...body,
        budget_min: body.budget_min || null,
        budget_max: body.budget_max || null,
      })
      setSettings(saved)
      setPrefs(saved)
      setPrefsState('saved')
    } catch (err) { setPrefsState((err as Error).message) }
  }

  const setTheme = async (theme: Settings['theme']) => {
    setPrefs(p => ({ ...p, theme }))
    setSettings({ ...settings, theme })  // apply instantly
    await savePrefs({ theme })
  }

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPwState('saving')
    try {
      await api.changePassword(user.has_password ? current : null, next)
      setCurrent(''); setNext('')
      setPwState('saved')
      setSession(await api.me())
    } catch (err) { setPwState((err as Error).message) }
  }

  const addInterest = () => {
    const v = interest.trim()
    if (v && !prefs.interests.includes(v)) setPrefs(p => ({ ...p, interests: [...p.interests, v].slice(0, 15) }))
    setInterest('')
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-8 sm:py-10">
        <h1 className="font-serif text-4xl font-semibold tracking-tight">Settings</h1>

        {/* Profile */}
        <Card title="Profile">
          <form onSubmit={saveProfile} className="flex flex-col gap-5 sm:flex-row sm:items-start">
            <Avatar name={user.name} url={user.avatar_url} className="size-16 text-xl" />
            <div className="flex-1 space-y-4">
              <label className="block text-sm font-medium">Name
                <input className={`${field} mt-1.5`} value={name} onChange={e => { setName(e.target.value); setProfileState('idle') }} maxLength={80} required />
              </label>
              <div className="text-sm">
                <div className="font-medium">Email</div>
                <div className="mt-1 text-muted">{user.email}</div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
                  {user.has_password && <span className="rounded-full bg-surface-2 px-2 py-0.5">Password</span>}
                  {user.google_linked && <span className="rounded-full bg-surface-2 px-2 py-0.5">Google</span>}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button type="submit" disabled={name.trim() === user.name} className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-40">Save profile</button>
                <Status state={profileState} />
              </div>
            </div>
          </form>
        </Card>

        {/* Travel preferences */}
        <Card title="Travel preferences" desc="Used as defaults for every new trip. Anything you say in a request overrides them.">
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="block text-sm font-medium sm:col-span-2">Home city
              <input className={`${field} mt-1.5`} placeholder="e.g. Hyderabad" value={prefs.home_city ?? ''} maxLength={80}
                onChange={e => setPrefs(p => ({ ...p, home_city: e.target.value }))} autoComplete="address-level2" />
              <span className="mt-1 block text-xs font-normal text-faint">Where your trips usually start. Used to compare flights, trains, buses and driving.</span>
            </label>
            <label className="block text-sm font-medium">Home currency
              <select className={`${field} mt-1.5`} value={prefs.home_currency} onChange={e => setPrefs(p => ({ ...p, home_currency: e.target.value }))}>
                {CURRENCIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">Usual number of travellers
              <input type="number" min={1} max={20} className={`${field} mt-1.5`} value={prefs.default_travelers}
                onChange={e => setPrefs(p => ({ ...p, default_travelers: Math.max(1, Math.min(20, Number(e.target.value) || 1)) }))} />
            </label>
            <div className="sm:col-span-2">
              <div className="text-sm font-medium">Typical trip budget ({prefs.home_currency}, total)</div>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                <input inputMode="numeric" aria-label="Minimum budget" placeholder="Min" className={field} value={prefs.budget_min ?? ''}
                  onChange={e => setPrefs(p => ({ ...p, budget_min: e.target.value ? Number(e.target.value.replace(/\D/g, '')) : null }))} />
                <input inputMode="numeric" aria-label="Maximum budget" placeholder="Max" className={field} value={prefs.budget_max ?? ''}
                  onChange={e => setPrefs(p => ({ ...p, budget_max: e.target.value ? Number(e.target.value.replace(/\D/g, '')) : null }))} />
              </div>
              <p className="mt-1 text-xs text-faint">Fills the 🎯 Your budget option when a request doesn't mention a budget.</p>
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1.5 text-sm font-medium">Travel style</div>
              <Segmented label="Travel style" value={prefs.travel_style} onChange={v => setPrefs(p => ({ ...p, travel_style: v }))}
                options={[{ value: 'budget', label: '💰 Budget' }, { value: 'balanced', label: '⚖️ Balanced' }, { value: 'luxury', label: '💎 Luxury' }]} />
            </div>
            <div className="sm:col-span-2">
              <div className="mb-1.5 text-sm font-medium">Pace</div>
              <Segmented label="Pace" value={prefs.pace} onChange={v => setPrefs(p => ({ ...p, pace: v }))}
                options={[{ value: 'relaxed', label: 'Relaxed' }, { value: 'moderate', label: 'Moderate' }, { value: 'packed', label: 'Packed' }]} />
            </div>
            <div className="sm:col-span-2">
              <div className="text-sm font-medium">Interests</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {prefs.interests.map(i => (
                  <span key={i} className="flex items-center gap-1 rounded-full bg-accent-soft py-1 pr-1.5 pl-3 text-sm text-accent">
                    {i}
                    <button type="button" aria-label={`Remove ${i}`} onClick={() => setPrefs(p => ({ ...p, interests: p.interests.filter(x => x !== i) }))}
                      className="rounded-full p-0.5 hover:bg-accent hover:text-accent-ink"><X className="size-3" /></button>
                  </span>
                ))}
              </div>
              <div className="mt-2 flex gap-2">
                <input className={field} placeholder="Add an interest, e.g. street food" value={interest} maxLength={40}
                  onChange={e => setInterest(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addInterest() } }} />
                <button type="button" onClick={addInterest} className="shrink-0 rounded-xl border border-line px-4 text-sm font-medium hover:border-accent/50">Add</button>
              </div>
            </div>
            <label className="block text-sm font-medium sm:col-span-2">Dietary needs
              <input className={`${field} mt-1.5`} placeholder="e.g. vegetarian, no pork, nut allergy" value={prefs.dietary} maxLength={120}
                onChange={e => setPrefs(p => ({ ...p, dietary: e.target.value }))} />
            </label>
          </div>
          <div className="mt-6 flex items-center gap-3">
            <button type="button" onClick={() => savePrefs()} className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink">Save preferences</button>
            <Status state={prefsState} />
          </div>
        </Card>

        {/* Appearance */}
        <Card title="Appearance">
          <Segmented label="Theme" value={prefs.theme} onChange={setTheme}
            options={[{ value: 'system', label: 'System', icon: Monitor }, { value: 'light', label: 'Light', icon: Sun }, { value: 'dark', label: 'Dark', icon: Moon }]} />
        </Card>

        {/* Security */}
        <Card title="Security" desc={user.has_password ? 'Changing your password signs out your other devices.' : 'Your account uses Google sign-in. You can also add a password.'}>
          <form onSubmit={changePassword} className="grid gap-4 sm:grid-cols-2">
            {user.has_password && (
              <label className="block text-sm font-medium">Current password
                <input type="password" className={`${field} mt-1.5`} value={current} onChange={e => setCurrent(e.target.value)} autoComplete="current-password" required />
              </label>
            )}
            <label className="block text-sm font-medium">New password
              <input type="password" className={`${field} mt-1.5`} value={next} onChange={e => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
            </label>
            <div className="flex items-center gap-3 sm:col-span-2">
              <button type="submit" className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-ink">{user.has_password ? 'Change password' : 'Set password'}</button>
              <Status state={pwState} />
            </div>
          </form>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
            <div>
              <div className="text-sm font-medium">Log out everywhere</div>
              <div className="text-xs text-muted">Ends every session, including this one.</div>
            </div>
            <button type="button" onClick={async () => { await api.logoutAll(); await logout(); navigate('/login') }}
              className="rounded-xl border border-line px-4 py-2 text-sm font-medium hover:border-accent/50">Log out everywhere</button>
          </div>
        </Card>

        {/* Danger */}
        {/* Your data (DPDP: right to access) */}
        <Card title="Your data" desc="Download everything TravelGenie stores about you: account, preferences, trips, conversations and uploaded documents.">
          <div className="flex flex-wrap items-center gap-3">
            <a href={api.accountExportUrl} download className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-sm font-medium hover:border-accent/50">
              <Download className="size-4" /> Download my data (JSON)
            </a>
            <span className="text-xs text-muted">
              Read the <Link to="/privacy" className="text-accent hover:underline">Privacy Policy</Link> and{' '}
              <Link to="/terms" className="text-accent hover:underline">Terms of Use</Link>.
            </span>
          </div>
        </Card>

        <Card danger title="Delete account" desc="Permanently deletes your account, settings, all trips and their conversations, and your uploaded documents. This can't be undone.">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input className={field} placeholder='Type DELETE to confirm' value={confirmText} onChange={e => setConfirmText(e.target.value)} aria-label="Type DELETE to confirm" />
            <button type="button" disabled={confirmText !== 'DELETE' || deleting}
              onClick={async () => { setDeleting(true); await api.deleteAccount(); await logout(); navigate('/signup') }}
              className="shrink-0 rounded-xl bg-bad px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
              {deleting ? 'Deleting…' : 'Delete my account'}
            </button>
          </div>
        </Card>
      </div>
    </div>
  )
}
