import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Square } from 'lucide-react'

interface Props {
  busy: boolean
  disabled?: boolean
  onSend: (text: string) => void
  onStop: () => void
  autoFocus?: boolean
  placeholder?: string
}

export function Composer({ busy, disabled, onSend, onStop, autoFocus, placeholder }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [text])

  useEffect(() => { if (autoFocus) ref.current?.focus() }, [autoFocus])

  const submit = () => {
    const t = text.trim()
    if (!t || busy || disabled) return
    onSend(t)
    setText('')
  }

  return (
    <form
      onSubmit={e => { e.preventDefault(); submit() }}
      className="rounded-2xl border border-line bg-surface p-2 shadow-[0_8px_30px_-12px_rgba(0,0,0,0.25)] focus-within:border-accent/60"
    >
      <label htmlFor="composer" className="sr-only">Message TravelGenie</label>
      <textarea
        id="composer"
        ref={ref}
        rows={1}
        value={text}
        disabled={disabled}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder={placeholder ?? 'Where to? Add dates, budget and travel style…'}
        className="block max-h-[220px] w-full resize-none bg-transparent px-2.5 py-2 text-[15px] text-ink placeholder:text-faint focus:outline-none disabled:cursor-not-allowed"
      />
      <div className="flex items-center justify-between px-1.5 pt-1">
        <span className="text-xs text-faint">Enter to send · Shift+Enter for new line</span>
        {busy ? (
          <button type="button" onClick={onStop} aria-label="Stop generating"
            className="grid size-8 place-items-center rounded-lg bg-ink text-bg transition hover:opacity-80">
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button type="submit" aria-label="Send" disabled={!text.trim() || disabled}
            className="grid size-8 place-items-center rounded-lg bg-accent text-accent-ink transition hover:opacity-90 disabled:opacity-30">
            <ArrowUp className="size-4" />
          </button>
        )}
      </div>
    </form>
  )
}
