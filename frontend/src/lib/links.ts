// Links that open well-known booking and map sites with the trip details filled in.
// Plain public URLs: no accounts, API keys or partner approvals needed.

export interface ExternalLink {
  label: string
  url: string
}

const enc = encodeURIComponent
const slug = (s: string) => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

function addDays(isoDate: string, days: number) {
  const d = new Date(`${isoDate}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Google Maps search for a place ("Basilica of Bom Jesus, Old Goa, Goa"). */
export function mapsPlace(name: string, ...context: (string | null | undefined)[]) {
  const q = [name, ...context.filter(Boolean)].join(', ')
  return `https://www.google.com/maps/search/?api=1&query=${enc(q)}`
}

export function mapsDirections(origin: string, destination: string, mode: 'driving' | 'transit' = 'driving') {
  return `https://www.google.com/maps/dir/?api=1&origin=${enc(origin)}&destination=${enc(destination)}&travelmode=${mode}`
}

/** Where to book a way of getting from `origin` to `destination`. */
export function transportLinks(mode: string, origin: string, destination: string,
  date?: string | null, travelers = 1): ExternalLink[] {
  switch (mode) {
    case 'flight': {
      const when = date ? ` on ${date}` : ''
      const who = travelers > 1 ? ` for ${travelers} adults` : ''
      return [
        { label: 'Google Flights', url: `https://www.google.com/travel/flights?q=${enc(`Flights from ${origin} to ${destination}${when}${who}`)}` },
      ]
    }
    case 'train':
      return [
        { label: 'IRCTC', url: 'https://www.irctc.co.in/nget/train-search' },
        { label: 'Trains on this route', url: `https://www.google.com/search?q=${enc(`trains from ${origin} to ${destination}`)}` },
      ]
    case 'bus':
      return [{ label: 'redBus', url: `https://www.redbus.in/bus-tickets/${slug(origin)}-to-${slug(destination)}` }]
    case 'car':
      return [{ label: 'Directions', url: mapsDirections(origin, destination, 'driving') }]
    case 'ferry':
      return [{ label: 'Ferry options', url: `https://www.google.com/search?q=${enc(`ferry from ${origin} to ${destination}`)}` }]
    default:
      return []
  }
}

/** Find a stay on Booking.com (with dates and guests when known) and on Google Maps. */
export function stayLinks(name: string, area: string | null | undefined, destination: string,
  checkin?: string | null, nights?: number, adults = 1): ExternalLink[] {
  const params = new URLSearchParams({ ss: [name, area, destination].filter(Boolean).join(', ') })
  if (checkin && nights) {
    params.set('checkin', checkin)
    params.set('checkout', addDays(checkin, nights))
  }
  params.set('group_adults', String(Math.max(adults, 1)))
  params.set('no_rooms', '1')
  return [
    { label: 'Booking.com', url: `https://www.booking.com/searchresults.html?${params}` },
    { label: 'Google Maps', url: mapsPlace(name, area, destination) },
  ]
}
