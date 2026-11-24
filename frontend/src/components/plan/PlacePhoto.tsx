import { useState } from 'react'
import { ImageOff } from 'lucide-react'
import type { Place } from '../../lib/api'

/** A real, credited photo of a place (Wikimedia Commons). "Area photo" when it shows the surroundings. */
export function PlacePhoto({ place, className = '', size = 'thumb', label = true }: {
  place?: Place | null
  className?: string
  size?: 'thumb' | 'url'
  label?: boolean
}) {
  const [failed, setFailed] = useState(false)
  const photo = place?.photo
  if (!photo || failed) {
    return (
      <div className={`grid place-items-center bg-surface-2 text-faint ${className}`} aria-hidden>
        <ImageOff className="size-5" />
      </div>
    )
  }
  return (
    <figure className={`relative overflow-hidden bg-surface-2 ${className}`}>
      <img src={photo[size]} alt={place?.name ?? ''} loading="lazy" decoding="async" referrerPolicy="no-referrer"
        onError={() => setFailed(true)} className="size-full object-cover" />
      {label && (
        <figcaption className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/60 to-transparent px-1.5 pt-4 pb-1 text-[10px] text-white/90">
          <span className="font-medium">{photo.kind === 'area' ? 'Area photo' : ''}</span>
          <a href={photo.page} target="_blank" rel="noopener noreferrer" className="hover:underline" onClick={e => e.stopPropagation()}>
            © {photo.credit}
          </a>
        </figcaption>
      )}
    </figure>
  )
}
