import { useEffect, useRef, useState } from 'react'
import { Check, Copy, Link2, Loader2, Share2, X } from 'lucide-react'
import { api } from '../../lib/api'

/** WhatsApp's own icon is a brand mark, so a plain chat-bubble glyph stands in. */
function WhatsAppGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
      <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1-.7.8-.8 1-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3a.5.5 0 0 0 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 2.9 2.9 0 0 0-.9 2.2 5 5 0 0 0 1 2.7 11.5 11.5 0 0 0 4.4 3.9c1.6.7 2.3.8 3.1.6a2.7 2.7 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c0-.1-.2-.2-.4-.3Z" />
    </svg>
  )
}

export function ShareMenu({ tripId, title, initialToken }: { tripId: string; title: string; initialToken: string | null }) {
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState<string | null>(initialToken)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => { setToken(initialToken) }, [initialToken])
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [open])

  const url = token ? `${window.location.origin}/share/${token}` : ''
  const message = `${title}: my trip plan on TravelGenie ✈️ ${url}`

  const create = async () => {
    setBusy(true)
    setError(null)
    try { setToken((await api.shareTrip(tripId)).token) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const revoke = async () => {
    setBusy(true)
    try { await api.unshareTrip(tripId); setToken(null) } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* blocked */ }
  }
  const nativeShare = async () => {
    try { await navigator.share({ title, text: `${title}: my trip plan on TravelGenie`, url }) } catch { /* cancelled */ }
  }

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} aria-haspopup="dialog"
        className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:border-accent/50">
        <Share2 className="size-4" /> Share
      </button>
      {open && (
        <div role="dialog" aria-label="Share trip" className="absolute right-0 z-[500] mt-1.5 w-[min(340px,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-4 shadow-xl">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-semibold">Share this trip</h3>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="rounded p-0.5 text-faint hover:text-ink"><X className="size-4" /></button>
          </div>
          {!token ? (
            <>
              <p className="mt-1.5 text-sm text-muted">
                Anyone with the link can view the plan (options, itinerary, map). Your chat and private documents are never shared.
              </p>
              <button type="button" onClick={create} disabled={busy}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-60">
                {busy ? <Loader2 className="size-4 animate-spin" /> : <Link2 className="size-4" />} Create public link
              </button>
            </>
          ) : (
            <>
              <div className="mt-3 flex gap-1.5">
                <input readOnly value={url} aria-label="Share link" onFocus={e => e.currentTarget.select()}
                  className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-2.5 py-1.5 text-xs" />
                <button type="button" onClick={copy} className="flex shrink-0 items-center gap-1 rounded-lg border border-line px-2.5 text-xs font-medium hover:border-accent/50">
                  {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />} {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-center gap-1.5 rounded-xl bg-[#1fa855] px-3 py-2 text-sm font-medium text-white hover:opacity-90">
                  <WhatsAppGlyph /> WhatsApp
                </a>
                {typeof navigator.share === 'function' ? (
                  <button type="button" onClick={nativeShare} className="flex items-center justify-center gap-1.5 rounded-xl border border-line px-3 py-2 text-sm font-medium hover:border-accent/50">
                    <Share2 className="size-4" /> More…
                  </button>
                ) : (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-1.5 rounded-xl border border-line px-3 py-2 text-sm font-medium hover:border-accent/50">
                    <Link2 className="size-4" /> Open
                  </a>
                )}
              </div>
              <button type="button" onClick={revoke} disabled={busy} className="mt-3 text-xs text-bad hover:underline disabled:opacity-60">
                Stop sharing (the link stops working)
              </button>
            </>
          )}
          {error && <p role="alert" className="mt-2 text-xs text-bad">{error}</p>}
        </div>
      )}
    </div>
  )
}
