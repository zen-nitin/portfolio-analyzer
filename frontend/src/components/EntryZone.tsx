import { useState } from 'react'
import { useSetEntryZone } from '../hooks/useWatchlist'
import { formatPrice } from '../utils/format'
import type { WatchlistItem, MarketQuote } from '../api/types'

// Where the live price sits relative to the buy zone.
export type ZoneStatus = 'in' | 'below' | 'above'

export function zoneStatus(item: WatchlistItem, price: number | null): ZoneStatus | null {
  if (price == null) return null
  if (item.entry_low == null && item.entry_high == null) return null
  const lo = item.entry_low ?? -Infinity
  const hi = item.entry_high ?? Infinity
  if (price < lo) return 'below'
  if (price > hi) return 'above'
  return 'in'
}

export const ZONE_BADGE: Record<ZoneStatus, { label: string; color: string }> = {
  in: { label: '● In buy zone', color: 'var(--positive)' },
  below: { label: '▼ Below zone', color: '#4af6c3' }, // cheaper than target — an opportunity
  above: { label: '▲ Above zone', color: 'var(--text-muted)' },
}

export function zoneText(item: WatchlistItem): string {
  const { entry_low: lo, entry_high: hi } = item
  if (lo != null && hi != null) return `${formatPrice(lo)}–${formatPrice(hi)}`
  if (hi != null) return `≤ ${formatPrice(hi)}`
  if (lo != null) return `≥ ${formatPrice(lo)}`
  return ''
}

/**
 * Display + inline-edit a watchlist item's buy entry zone. Shared by the
 * Watchlist page and the dashboard widget. `compact` shrinks it for the
 * narrower dashboard column.
 */
export default function EntryZoneControl({
  item,
  quote,
  compact = false,
}: {
  item: WatchlistItem
  quote?: MarketQuote
  compact?: boolean
}) {
  const setZone = useSetEntryZone()
  const [editing, setEditing] = useState(false)
  const [low, setLow] = useState('')
  const [high, setHigh] = useState('')

  const hasZone = item.entry_low != null || item.entry_high != null
  const status = zoneStatus(item, quote?.last_price ?? null)

  function startEdit() {
    setLow(item.entry_low != null ? String(item.entry_low) : '')
    setHigh(item.entry_high != null ? String(item.entry_high) : '')
    setEditing(true)
  }

  async function save() {
    const lo = low.trim() === '' ? null : Number(low)
    const hi = high.trim() === '' ? null : Number(high)
    if ((lo !== null && !Number.isFinite(lo)) || (hi !== null && !Number.isFinite(hi))) return
    await setZone.mutateAsync({ id: item.id, entry_low: lo, entry_high: hi })
    setEditing(false)
  }

  async function clearZone() {
    await setZone.mutateAsync({ id: item.id, entry_low: null, entry_high: null })
    setEditing(false)
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') save()
    if (e.key === 'Escape') setEditing(false)
  }

  const labelSize = compact ? 11 : 11.5
  const linkSize = compact ? 10.5 : 11

  if (editing) {
    return (
      <div style={{ marginTop: compact ? 4 : 6, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Buy zone ₹</span>
        <input
          className="form-input"
          type="number"
          step="any"
          placeholder="low"
          autoFocus
          style={{ width: compact ? 64 : 78, padding: '4px 6px', fontSize: 12 }}
          value={low}
          onChange={(e) => setLow(e.target.value)}
          onKeyDown={onKey}
        />
        <span style={{ color: 'var(--text-muted)' }}>–</span>
        <input
          className="form-input"
          type="number"
          step="any"
          placeholder="high"
          style={{ width: compact ? 64 : 78, padding: '4px 6px', fontSize: 12 }}
          value={high}
          onChange={(e) => setHigh(e.target.value)}
          onKeyDown={onKey}
        />
        <button className="btn btn-primary btn-sm" onClick={save} disabled={setZone.isPending}>
          {setZone.isPending ? '…' : '✓'}
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>✕</button>
        {hasZone && (
          <button className="btn btn-danger btn-sm" onClick={clearZone} disabled={setZone.isPending}>
            Clear
          </button>
        )}
      </div>
    )
  }

  return (
    <div style={{ marginTop: compact ? 4 : 6, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {hasZone ? (
        <>
          <span style={{ fontSize: labelSize }}>
            <span style={{ color: 'var(--text-muted)' }}>Entry </span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{zoneText(item)}</span>
          </span>
          {status && (
            <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.3px', color: ZONE_BADGE[status].color }}>
              {ZONE_BADGE[status].label}
            </span>
          )}
          <button type="button" className="link-button" style={{ fontSize: linkSize, color: 'var(--accent)' }} onClick={startEdit}>
            Edit
          </button>
        </>
      ) : (
        <button type="button" className="link-button" style={{ fontSize: linkSize, color: 'var(--accent)' }} onClick={startEdit}>
          + Entry zone
        </button>
      )}
    </div>
  )
}
