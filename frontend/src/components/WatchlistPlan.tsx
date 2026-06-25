import { useState } from 'react'
import { useSetPlan } from '../hooks/useWatchlist'
import type { WatchlistItem } from '../api/types'

/**
 * Display + inline-edit a watchlist item's trade-plan notes: the **catalyst**
 * (why you'd buy) and **exit when** (what would make you sell). Mirrors
 * EntryZoneControl. `compact` shrinks it for the narrower dashboard column.
 */
export default function PlanControl({
  item,
  compact = false,
}: {
  item: WatchlistItem
  compact?: boolean
}) {
  const setPlan = useSetPlan()
  const [editing, setEditing] = useState(false)
  const [catalyst, setCatalyst] = useState('')
  const [exitWhen, setExitWhen] = useState('')

  const hasPlan = Boolean(item.catalyst || item.exit_when)

  function startEdit() {
    setCatalyst(item.catalyst ?? '')
    setExitWhen(item.exit_when ?? '')
    setEditing(true)
  }

  async function save() {
    const c = catalyst.trim() === '' ? null : catalyst.trim()
    const e = exitWhen.trim() === '' ? null : exitWhen.trim()
    await setPlan.mutateAsync({ id: item.id, catalyst: c, exit_when: e })
    setEditing(false)
  }

  async function clearPlan() {
    await setPlan.mutateAsync({ id: item.id, catalyst: null, exit_when: null })
    setEditing(false)
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') save()
    if (e.key === 'Escape') setEditing(false)
  }

  const labelSize = compact ? 11 : 11.5
  const linkSize = compact ? 10.5 : 11
  const rowLabelStyle: React.CSSProperties = {
    fontSize: 11,
    color: 'var(--text-muted)',
    width: 58,
    flexShrink: 0,
  }

  if (editing) {
    return (
      <div style={{ marginTop: compact ? 4 : 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={rowLabelStyle}>Catalyst</span>
          <input
            className="form-input"
            placeholder="Why you'd buy — e.g. Q3 results, order win"
            autoFocus
            style={{ flex: 1, minWidth: 0, padding: '4px 6px', fontSize: 12 }}
            value={catalyst}
            onChange={(e) => setCatalyst(e.target.value)}
            onKeyDown={onKey}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={rowLabelStyle}>Exit when</span>
          <input
            className="form-input"
            placeholder="What would make you sell"
            style={{ flex: 1, minWidth: 0, padding: '4px 6px', fontSize: 12 }}
            value={exitWhen}
            onChange={(e) => setExitWhen(e.target.value)}
            onKeyDown={onKey}
          />
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={setPlan.isPending}>
            {setPlan.isPending ? '…' : '✓ Save'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>✕</button>
          {hasPlan && (
            <button className="btn btn-danger btn-sm" onClick={clearPlan} disabled={setPlan.isPending}>
              Clear
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ marginTop: compact ? 4 : 6 }}>
      {hasPlan ? (
        <div style={{ fontSize: labelSize, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {item.catalyst && (
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Catalyst: </span>
              {item.catalyst}
            </div>
          )}
          {item.exit_when && (
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Exit when: </span>
              {item.exit_when}
            </div>
          )}
          <button
            type="button"
            className="link-button"
            style={{ fontSize: linkSize, color: 'var(--accent)', alignSelf: 'flex-start' }}
            onClick={startEdit}
          >
            Edit
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="link-button"
          style={{ fontSize: linkSize, color: 'var(--accent)' }}
          onClick={startEdit}
        >
          + Catalyst / exit
        </button>
      )}
    </div>
  )
}
