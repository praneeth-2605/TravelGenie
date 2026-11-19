import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Loader2, MapPinned, Sparkles, Wallet } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void
          renderButton: (el: HTMLElement, o: Record<string, unknown>) => void
        }
      }
    }
  }
}

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('Could not load Google sign-in'))
    document.head.appendChild(s)
  })
}

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { setSession } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const next = (location.state as { from?: string } | null)?.from ?? '/'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [googleId, setGoogleId] = useState<string | null>(null)
  const googleBtn = useRef<HTMLDivElement>(null)

  useEffect(() => { api.authConfig().then(c => setGoogleId(c.google_client_id)).catch(() => {}) }, [])

  useEffect(() => {
    if (!googleId || !googleBtn.current) return
    let cancelled = false
    loadGoogleScript().then(() => {
      if (cancelled || !window.google || !googleBtn.current) return
      window.google.accounts.id.initialize({
        client_id: googleId,
        callback: async ({ credential }) => {
          setBusy(true)
          setError(null)
          try {
            setSession(await api.google(credential))
            navigate(next, { replace: true })
          } catch (e) {
            setError((e as Error).message)
          } finally {
            setBusy(false)
          }
        },
      })
      window.google.accounts.id.renderButton(googleBtn.current, {
        theme: document.documentElement.dataset.theme === 'dark' ? 'filled_black' : 'outline',
        size: 'large', width: googleBtn.current.offsetWidth || 360, text: mode === 'signup' ? 'signup_with' : 'continue_with',
        shape: 'pill',
      })
    }).catch(() => setGoogleId(null))
    return () => { cancelled = true }
  }, [googleId, mode, navigate, next, setSession])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setSession(mode === 'signup' ? await api.signup(name, email, password) : await api.login(email, password))
      navigate(next, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const input = 'mt-1.5 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none'

  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-[#13201d] p-12 text-[#f6efe4] lg:flex lg:flex-col">
        <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_80%_110%,rgba(226,118,82,0.45),transparent_60%),radial-gradient(90%_60%_at_0%_0%,rgba(82,140,120,0.35),transparent_60%)]" />
        <div className="relative flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-8" />
          <span className="font-serif text-2xl font-semibold">TravelGenie</span>
        </div>
        <div className="relative mt-auto max-w-md">
          <h1 className="font-serif text-5xl leading-[1.05] font-semibold tracking-tight">Three ways to take every trip.</h1>
          <p className="mt-4 text-lg text-[#f6efe4]/75">
            Tell us where and for how long. A team of AI agents finds real stays and sights, then builds a
            budget, a luxury and a your-budget plan, day by day.
          </p>
          <ul className="mt-8 space-y-3 text-[15px] text-[#f6efe4]/85">
            <li className="flex gap-3"><Wallet className="size-5 text-[#e8a07f]" /> Budget, Luxury and Your-budget options side by side</li>
            <li className="flex gap-3"><MapPinned className="size-5 text-[#e8a07f]" /> Real hostels, hotels and sights on a map</li>
            <li className="flex gap-3"><Sparkles className="size-5 text-[#e8a07f]" /> Export to PDF, calendar or Markdown</li>
          </ul>
        </div>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-[400px]">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <img src="/favicon.svg" alt="" className="size-7" />
            <span className="font-serif text-xl font-semibold">TravelGenie</span>
          </div>
          <h2 className="font-serif text-3xl font-semibold tracking-tight">
            {mode === 'signup' ? 'Create your account' : 'Welcome back'}
          </h2>
          <p className="mt-1.5 text-muted">
            {mode === 'signup' ? 'Plan smarter trips in minutes.' : 'Log in to see your trips.'}
          </p>

          {googleId && (
            <>
              <div ref={googleBtn} className="mt-7 flex min-h-[44px] w-full justify-center" />
              <div className="my-6 flex items-center gap-3 text-xs text-faint">
                <span className="h-px flex-1 bg-line" /> or with email <span className="h-px flex-1 bg-line" />
              </div>
            </>
          )}

          <form onSubmit={submit} className={googleId ? '' : 'mt-8'}>
            {mode === 'signup' && (
              <label className="mb-4 block text-sm font-medium">
                Name
                <input className={input} value={name} onChange={e => setName(e.target.value)} required autoComplete="name" maxLength={80} />
              </label>
            )}
            <label className="mb-4 block text-sm font-medium">
              Email
              <input className={input} type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" />
            </label>
            <label className="block text-sm font-medium">
              Password
              <div className="relative">
                <input className={`${input} pr-11`} type={show ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)} required minLength={mode === 'signup' ? 8 : 1}
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} />
                <button type="button" onClick={() => setShow(s => !s)} aria-label={show ? 'Hide password' : 'Show password'}
                  className="absolute top-1/2 right-2 mt-0.5 -translate-y-1/2 rounded-lg p-1.5 text-faint hover:text-ink">
                  {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </label>
            {mode === 'signup' && <p className="mt-1.5 text-xs text-faint">At least 8 characters, with a number or symbol.</p>}

            {error && <p role="alert" className="mt-4 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}

            <button type="submit" disabled={busy}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 font-medium text-accent-ink transition hover:opacity-90 disabled:opacity-60">
              {busy && <Loader2 className="size-4 animate-spin" />}
              {mode === 'signup' ? 'Create account' : 'Log in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-muted">
            {mode === 'signup' ? 'Already have an account? ' : 'New to TravelGenie? '}
            <Link to={mode === 'signup' ? '/login' : '/signup'} state={location.state} className="font-medium text-accent hover:underline">
              {mode === 'signup' ? 'Log in' : 'Create an account'}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
