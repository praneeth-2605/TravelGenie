import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { TIER_META, type Marker as PlanMarker, type Tier, type TripPlan } from '../../lib/api'
import { DAY_COLORS } from './Timeline'

function sightIcon(day: number | undefined, label: string) {
  const color = day ? DAY_COLORS[(day - 1) % DAY_COLORS.length] : '#6f675c'
  return L.divIcon({
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -26],
    html: `<div style="width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);display:grid;place-items:center">
             <span style="transform:rotate(45deg);color:#fff;font:600 11px/1 'DM Sans',sans-serif">${label}</span></div>`,
  })
}

function stayIcon(highlight: boolean) {
  const size = highlight ? 34 : 26
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:10px;background:${highlight ? '#c8603f' : '#1d1a16'};border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);display:grid;place-items:center">
             <svg width="${size * 0.5}" height="${size * 0.5}" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/><path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/><path d="M12 4v6"/><path d="M2 18h20"/></svg></div>`,
  })
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 14 })
    else if (points.length === 1) map.setView(points[0], 13)
  }, [map, points])
  return null
}

function FocusOn({ marker, refs }: { marker: PlanMarker | undefined; refs: React.RefObject<Map<string, L.Marker>> }) {
  const map = useMap()
  useEffect(() => {
    if (!marker || marker.lat == null || marker.lon == null) return
    map.flyTo([marker.lat, marker.lon], Math.max(map.getZoom(), 15), { duration: 0.8 })
    const t = setTimeout(() => refs.current?.get(marker.id)?.openPopup(), 850)
    return () => clearTimeout(t)
  }, [map, marker, refs])
  return null
}

export function TripMap({ plan, selected, focusId }: { plan: TripPlan; selected: Tier; focusId: string | null }) {
  const refs = useRef(new Map<string, L.Marker>())
  const selectedStayId = plan.hotels?.[selected] ?? null
  const markers = plan.markers.filter(m => m.lat != null && m.lon != null)
  const points = useMemo(() => markers.map(m => [m.lat!, m.lon!] as [number, number]), [markers])
  const center: [number, number] = plan.map_center ? [plan.map_center.lat, plan.map_center.lon] : points[0] ?? [20, 0]

  // Number sights in visiting order across the trip.
  const order = new Map<string, number>()
  plan.days.forEach(d => d.stops.forEach(s => { if (s.place_id && s.kind !== 'meal' && !order.has(s.place_id)) order.set(s.place_id, order.size + 1) }))

  if (!markers.length && !plan.map_center) {
    return <div className="grid h-full place-items-center rounded-2xl border border-line bg-surface p-8 text-center text-muted">No mapped places for this trip yet.</div>
  }

  return (
    <div className="relative h-full min-h-[420px] overflow-hidden rounded-2xl border border-line">
      <MapContainer center={center} zoom={12} scrollWheelZoom className="h-full w-full" style={{ background: 'var(--surface-2)' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={points} />
        <FocusOn marker={markers.find(m => m.id === focusId)} refs={refs} />
        {markers.map(m => {
          const isStay = m.kind === 'stay'
          const highlight = isStay && m.id === selectedStayId
          return (
            <Marker
              key={m.id}
              position={[m.lat!, m.lon!]}
              icon={isStay ? stayIcon(highlight) : sightIcon(m.days?.[0], String(order.get(m.id) ?? '•'))}
              zIndexOffset={highlight ? 1000 : isStay ? 500 : 0}
              ref={el => { if (el) refs.current.set(m.id, el); else refs.current.delete(m.id) }}
            >
              <Popup>
                <div style={{ minWidth: 180, maxWidth: 220, fontFamily: 'DM Sans, sans-serif' }}>
                  {m.photo && (
                    <img src={m.photo.thumb} alt="" loading="lazy" referrerPolicy="no-referrer"
                      style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 8, marginBottom: 6 }} />
                  )}
                  <strong>{m.name}</strong>
                  <div style={{ fontSize: 12, color: '#6f675c', marginTop: 2 }}>
                    {isStay
                      ? `${highlight ? 'Your stay' : 'Stay option'} · ${(m.tiers ?? []).map(t => TIER_META[t]?.label).join(', ')}`
                      : `Day ${m.days?.join(', ')}${m.area ? ` · ${m.area}` : ''}`}
                  </div>
                  {m.price && <div style={{ fontSize: 12, marginTop: 4 }}>{m.price}</div>}
                  {m.hours && <div style={{ fontSize: 12 }}>{m.hours}</div>}
                  {m.description && <div style={{ fontSize: 12, marginTop: 4 }}>{m.description}</div>}
                  {m.url && <a href={m.url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Website ↗</a>}
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
      <div className="pointer-events-none absolute bottom-3 left-3 z-[400] flex flex-wrap gap-1.5">
        {plan.days.map(d => (
          <span key={d.day} className="flex items-center gap-1 rounded-full bg-surface/90 px-2 py-0.5 text-[11px] shadow backdrop-blur">
            <span className="size-2 rounded-full" style={{ background: DAY_COLORS[(d.day - 1) % DAY_COLORS.length] }} /> Day {d.day}
          </span>
        ))}
        <span className="flex items-center gap-1 rounded-full bg-surface/90 px-2 py-0.5 text-[11px] shadow backdrop-blur">
          <span className="size-2 rounded-sm bg-accent" /> Your stay
        </span>
      </div>
    </div>
  )
}
