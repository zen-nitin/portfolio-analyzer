import { useState } from 'react'
import {
  useWatchlist,
  useAddWatchlistItem,
  useDeleteWatchlistItem,
  useReorderWatchlist,
  useWatchlistSuggestions,
} from '../hooks/useWatchlist'
import { useAddWatchlistItem as useAddFromHook } from '../hooks/useWatchlist'
import { useAIProviders } from '../hooks/useInsights'
import { useWatchlistQuotes } from '../hooks/useMarket'
import { useStockModal } from '../context/StockModalContext'
import ExternalGenerate from '../components/ExternalGenerate'
import EntryZoneControl from '../components/EntryZone'
import { getWatchlistPrompt } from '../api/endpoints'
import QuoteChange from '../components/QuoteChange'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import type { WatchlistSuggestion, SuggestionBucket, WatchlistItem, MarketQuote } from '../api/types'

const BUCKET_META: Record<SuggestionBucket, { label: string; blurb: string; color: string }> = {
  CORE_GROWTH: {
    label: 'Core · long-term growth',
    blurb: 'Quality compounders to hold.',
    color: '#4af6c3',
  },
  TACTICAL: {
    label: 'Tactical · time-bound',
    blurb: 'Good for a window on a specific catalyst.',
    color: '#fb8b1e',
  },
  SWAP_CANDIDATE: {
    label: 'Swap · rotate in if a holding turns risky',
    blurb: 'Replacements for positions that may need exiting.',
    color: '#3b9dff',
  },
}

const RISK_COLOR: Record<string, string> = { LOW: '#4af6c3', MEDIUM: '#ffd33d', HIGH: '#ff433d' }

function SuggestionCard({
  s,
  onOpen,
  onAdd,
  adding,
}: {
  s: WatchlistSuggestion
  onOpen: (symbol: string, exchange: string) => void
  onAdd: (s: WatchlistSuggestion) => void
  adding: boolean
}) {
  return (
    <div className="suggestion-card">
      <div className="suggestion-info">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="link-button suggestion-symbol"
            onClick={() => onOpen(s.symbol, s.exchange)}
          >
            {s.symbol}
          </button>
          <span className="suggestion-exchange">{s.exchange}</span>
          {s.risk && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.5px',
                color: RISK_COLOR[s.risk] ?? 'var(--text-muted)',
                border: `1px solid ${RISK_COLOR[s.risk] ?? 'var(--border)'}`,
                borderRadius: 4,
                padding: '1px 5px',
              }}
            >
              {s.risk} RISK
            </span>
          )}
          {s.horizon && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>· {s.horizon}</span>
          )}
        </div>
        <div className="suggestion-rationale">{s.rationale}</div>
        {s.bucket === 'TACTICAL' && s.catalyst && (
          <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
            <strong>Catalyst:</strong> {s.catalyst}
            {s.exit_trigger && (
              <>
                <br />
                <strong>Exit when:</strong> {s.exit_trigger}
              </>
            )}
          </div>
        )}
        {s.bucket === 'SWAP_CANDIDATE' && s.replaces && (
          <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
            <strong>Replaces:</strong> {s.replaces}
          </div>
        )}
      </div>
      <button
        className="btn btn-secondary btn-sm"
        onClick={() => onAdd(s)}
        disabled={adding}
      >
        + Add
      </button>
    </div>
  )
}

function WatchlistRow({
  item,
  quote,
  quoteLoading,
  onOpen,
  onDelete,
  deleting,
  drag,
}: {
  item: WatchlistItem
  quote: MarketQuote | undefined
  quoteLoading: boolean
  onOpen: (symbol: string, exchange: string) => void
  onDelete: (id: string) => void
  deleting: boolean
  drag: {
    onStart: (id: string) => void
    onEnter: (id: string) => void
    onEnd: () => void
    onDrop: (targetId: string, sourceId: string) => void
    isDragging: boolean
    isOver: boolean
  }
}) {
  return (
    <div
      className="watchlist-item"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        // Carry the id in the drag payload so the drop handler never depends on
        // React state that may not have re-rendered yet.
        e.dataTransfer.setData('text/plain', item.id)
        drag.onStart(item.id)
      }}
      onDragEnter={() => drag.onEnter(item.id)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        drag.onDrop(item.id, e.dataTransfer.getData('text/plain'))
      }}
      onDragEnd={drag.onEnd}
      style={{
        flexWrap: 'wrap',
        opacity: drag.isDragging ? 0.4 : 1,
        borderTop: drag.isOver ? '2px solid var(--accent)' : undefined,
        cursor: 'grab',
      }}
    >
      <span
        className="wl-grip"
        title="Drag to reorder"
        aria-hidden="true"
        style={{ color: 'var(--text-muted)', fontSize: 15, lineHeight: 1, cursor: 'grab', userSelect: 'none', alignSelf: 'flex-start', marginTop: 2 }}
      >
        ⠿
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div>
          <button
            type="button"
            className="link-button wl-symbol"
            onClick={() => onOpen(item.symbol, item.exchange)}
          >
            {item.symbol}
          </button>
          <span className="wl-exchange">{item.exchange}</span>
        </div>
        {item.note && <div className="wl-note">{item.note}</div>}
        <EntryZoneControl item={item} quote={quote} />
      </div>
      <div style={{ minWidth: 130 }}>
        <QuoteChange quote={quote} loading={quoteLoading} />
      </div>
      <button
        className="btn btn-danger btn-sm"
        onClick={() => onDelete(item.id)}
        disabled={deleting}
      >
        Remove
      </button>
    </div>
  )
}

export default function WatchlistPage() {
  const { data: items, isLoading, isError, error } = useWatchlist()
  const quotesQ = useWatchlistQuotes(items)
  const { openStock } = useStockModal()
  const addMutation = useAddWatchlistItem()
  const deleteMutation = useDeleteWatchlistItem()
  const reorderMutation = useReorderWatchlist()
  const suggest = useWatchlistSuggestions()
  const addFromSuggestion = useAddFromHook()
  const providersQ = useAIProviders()

  const [form, setForm] = useState({ symbol: '', exchange: 'NSE', note: '', entryLow: '', entryHigh: '' })
  const [formError, setFormError] = useState('')

  // Drag-to-reorder state.
  const [dragId, setDragId] = useState<string | null>(null)
  const [overId, setOverId] = useState<string | null>(null)

  function handleReorderDrop(targetId: string, sourceId: string) {
    setOverId(null)
    setDragId(null)
    // ids can arrive as numbers (backend) or strings (drag payload) — compare as strings.
    const source = String(sourceId || dragId || '')
    const target = String(targetId)
    if (!items || !source || source === target) return
    const ids = items.map((i) => String(i.id))
    const from = ids.indexOf(source)
    const to = ids.indexOf(target)
    if (from === -1 || to === -1) return
    const next = [...ids]
    next.splice(from, 1)
    next.splice(to, 0, source)
    reorderMutation.mutate(next)
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setFormError('')
    if (!form.symbol.trim()) {
      setFormError('Symbol is required.')
      return
    }
    const entryLow = form.entryLow.trim() === '' ? null : Number(form.entryLow)
    const entryHigh = form.entryHigh.trim() === '' ? null : Number(form.entryHigh)
    if ((entryLow !== null && !Number.isFinite(entryLow)) || (entryHigh !== null && !Number.isFinite(entryHigh))) {
      setFormError('Entry zone prices must be numbers.')
      return
    }
    try {
      await addMutation.mutateAsync({
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        note: form.note.trim(),
        entry_low: entryLow,
        entry_high: entryHigh,
      })
      setForm({ symbol: '', exchange: 'NSE', note: '', entryLow: '', entryHigh: '' })
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to add.')
    }
  }

  function handleDelete(id: string) {
    deleteMutation.mutate(id)
  }

  async function handleAddSuggestion(s: WatchlistSuggestion) {
    await addFromSuggestion.mutateAsync({
      symbol: s.symbol,
      exchange: s.exchange,
      note: s.rationale.slice(0, 200),
    })
  }

  const aiConfigured = (providersQ.data ?? []).some((p) => p.active && p.configured)
  const isAIUnavailable = providersQ.data !== undefined && !aiConfigured

  return (
    <div>
      <div className="page-header">
        <h1>Watchlist</h1>
      </div>

      <div className="two-col" style={{ alignItems: 'start' }}>
        {/* Left: watchlist items */}
        <div>
          <div className="section-title">Your Watchlist ({items?.length ?? 0})</div>

          {isLoading && <LoadingState message="Loading watchlist…" />}
          {isError && <ErrorState error={error} context="Watchlist" />}

          {!isLoading && !isError && items?.length === 0 && (
            <EmptyState
              icon="◎"
              title="Watchlist is empty"
              description="Add symbols below or get AI suggestions."
            />
          )}

          {items && items.length > 1 && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', margin: '0 0 8px' }}>
              Drag the ⠿ handle to reorder.
            </div>
          )}

          <div className="watchlist-list">
            {items?.map((item) => {
              const quote = quotesQ.data?.[`${item.symbol.toUpperCase()}:${item.exchange.toUpperCase()}`]
              return (
                <WatchlistRow
                  key={item.id}
                  item={item}
                  quote={quote}
                  quoteLoading={quotesQ.isLoading}
                  onOpen={openStock}
                  onDelete={handleDelete}
                  deleting={deleteMutation.isPending}
                  drag={{
                    onStart: setDragId,
                    onEnter: setOverId,
                    onEnd: () => {
                      setDragId(null)
                      setOverId(null)
                    },
                    onDrop: handleReorderDrop,
                    isDragging: dragId === item.id,
                    isOver: overId === item.id && dragId !== item.id,
                  }}
                />
              )
            })}
          </div>

          {/* Add form */}
          <div className="card" style={{ marginTop: 20 }}>
            <div className="card-title">Add to Watchlist</div>
            <form onSubmit={handleAdd}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, marginBottom: 10 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Symbol</label>
                  <input
                    className="form-input"
                    placeholder="e.g. INFY"
                    value={form.symbol}
                    onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Exchange</label>
                  <select
                    className="form-select"
                    value={form.exchange}
                    onChange={(e) => setForm((f) => ({ ...f, exchange: e.target.value }))}
                  >
                    <option value="NSE">NSE</option>
                    <option value="BSE">BSE</option>
                    <option value="NFO">NFO</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Note (optional)</label>
                <input
                  className="form-input"
                  placeholder="Why are you watching this?"
                  value={form.note}
                  onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Entry zone (optional)</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    className="form-input"
                    type="number"
                    step="any"
                    placeholder="Buy from ₹"
                    style={{ flex: 1, minWidth: 0 }}
                    value={form.entryLow}
                    onChange={(e) => setForm((f) => ({ ...f, entryLow: e.target.value }))}
                  />
                  <span style={{ color: 'var(--text-muted)' }}>–</span>
                  <input
                    className="form-input"
                    type="number"
                    step="any"
                    placeholder="up to ₹"
                    style={{ flex: 1, minWidth: 0 }}
                    value={form.entryHigh}
                    onChange={(e) => setForm((f) => ({ ...f, entryHigh: e.target.value }))}
                  />
                </div>
              </div>
              {formError && <div className="error-state" style={{ marginBottom: 10 }}>{formError}</div>}
              <button
                type="submit"
                className="btn btn-primary"
                disabled={addMutation.isPending}
              >
                {addMutation.isPending ? 'Adding…' : '+ Add'}
              </button>
            </form>
          </div>
        </div>

        {/* Right: AI suggestions — auto-generated daily bench */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <div className="section-title" style={{ marginBottom: 0 }}>Daily Ideas</div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={suggest.refresh}
              disabled={suggest.isPending || !aiConfigured}
              title="Regenerate today's ideas"
            >
              {suggest.isPending ? '…' : '↻ Refresh'}
            </button>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', margin: '4px 0 12px' }}>
            10 auto-generated ideas/day · core growth, tactical catalysts, and swap candidates for
            risky holdings.
          </div>

          <ExternalGenerate
            label="suggestions"
            fetchPrompt={() => getWatchlistPrompt(10).then((r) => r.prompt)}
            onApply={suggest.applyManual}
          />

          {isAIUnavailable && (
            <div className="ai-unconfigured">
              <span>⚠</span>
              <span>AI provider not configured. Add an API key in <em>Accounts</em>.</span>
            </div>
          )}

          {!isAIUnavailable && suggest.isError && (
            <ErrorState error={suggest.error} context="Suggestions" />
          )}

          {!isAIUnavailable && suggest.isPending && (
            <LoadingState message="Generating today's ideas (batched to cut cost — may take a few minutes). You can leave this page; it'll keep going." />
          )}

          {/* Holdings the AI flagged as risky */}
          {suggest.data?.flagged_holdings && suggest.data.flagged_holdings.length > 0 && (
            <div
              className="card"
              style={{ borderColor: 'rgba(255,67,61,0.35)', marginBottom: 12 }}
            >
              <div className="card-title" style={{ color: 'var(--negative)' }}>
                ⚠ Positions flagged risky
              </div>
              {suggest.data.flagged_holdings.map((f) => (
                <div key={f.symbol} style={{ fontSize: 12.5, marginBottom: 4 }}>
                  <button
                    type="button"
                    className="link-button wl-symbol"
                    onClick={() => openStock(f.symbol, 'NSE')}
                  >
                    {f.symbol}
                  </button>
                  <span style={{ color: 'var(--text-secondary)' }}> — {f.reason}</span>
                </div>
              ))}
            </div>
          )}

          {/* Suggestions grouped by bucket */}
          {suggest.data?.suggestions && suggest.data.suggestions.length > 0 && (
            <div>
              {(Object.keys(BUCKET_META) as SuggestionBucket[]).map((bucket) => {
                const picks = suggest.data!.suggestions.filter(
                  (s) => (s.bucket ?? 'CORE_GROWTH') === bucket,
                )
                if (picks.length === 0) return null
                const meta = BUCKET_META[bucket]
                return (
                  <div key={bucket} style={{ marginBottom: 18 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: meta.color, display: 'inline-block' }} />
                      <span style={{ fontSize: 12.5, fontWeight: 700, letterSpacing: '0.3px' }}>{meta.label}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({picks.length})</span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{meta.blurb}</div>
                    <div className="suggestion-list">
                      {picks.map((s) => (
                        <SuggestionCard
                          key={`${s.symbol}-${s.exchange}`}
                          s={s}
                          onOpen={openStock}
                          onAdd={handleAddSuggestion}
                          adding={addFromSuggestion.isPending}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
