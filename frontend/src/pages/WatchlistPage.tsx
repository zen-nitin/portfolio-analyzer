import { useState } from 'react'
import {
  useWatchlist,
  useAddWatchlistItem,
  useDeleteWatchlistItem,
  useWatchlistSuggestions,
} from '../hooks/useWatchlist'
import { useAddWatchlistItem as useAddFromHook } from '../hooks/useWatchlist'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import { ApiError } from '../api/client'
import type { WatchlistSuggestion } from '../api/types'

export default function WatchlistPage() {
  const { data: items, isLoading, isError, error } = useWatchlist()
  const addMutation = useAddWatchlistItem()
  const deleteMutation = useDeleteWatchlistItem()
  const suggestMutation = useWatchlistSuggestions()
  const addFromSuggestion = useAddFromHook()

  const [form, setForm] = useState({ symbol: '', exchange: 'NSE', note: '' })
  const [formError, setFormError] = useState('')
  const [suggestionCount, setSuggestionCount] = useState(5)

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setFormError('')
    if (!form.symbol.trim()) {
      setFormError('Symbol is required.')
      return
    }
    try {
      await addMutation.mutateAsync({
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        note: form.note.trim(),
      })
      setForm({ symbol: '', exchange: 'NSE', note: '' })
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to add.')
    }
  }

  function handleDelete(id: string) {
    deleteMutation.mutate(id)
  }

  async function handleGetSuggestions() {
    suggestMutation.mutate(suggestionCount)
  }

  async function handleAddSuggestion(s: WatchlistSuggestion) {
    await addFromSuggestion.mutateAsync({
      symbol: s.symbol,
      exchange: s.exchange,
      note: s.rationale.slice(0, 200),
    })
  }

  const isAIUnavailable =
    suggestMutation.isError && suggestMutation.error instanceof ApiError && suggestMutation.error.status === 503

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

          <div className="watchlist-list">
            {items?.map((item) => (
              <div key={item.id} className="watchlist-item">
                <div style={{ flex: 1 }}>
                  <div>
                    <span className="wl-symbol">{item.symbol}</span>
                    <span className="wl-exchange">{item.exchange}</span>
                  </div>
                  {item.note && <div className="wl-note">{item.note}</div>}
                </div>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={() => handleDelete(item.id)}
                  disabled={deleteMutation.isPending}
                >
                  Remove
                </button>
              </div>
            ))}
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

        {/* Right: AI suggestions */}
        <div>
          <div className="section-title">AI Suggestions</div>

          {isAIUnavailable && (
            <div className="ai-unconfigured">
              <span>⚠</span>
              <span>AI provider not configured. Add an API key in <em>Accounts</em>.</span>
            </div>
          )}

          {!isAIUnavailable && suggestMutation.isError && (
            <ErrorState error={suggestMutation.error} context="Suggestions" />
          )}

          <div className="card">
            <div className="card-title">Get Suggestions</div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 0 }}>
              <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                <label className="form-label">Count</label>
                <input
                  type="number"
                  className="form-input"
                  min={1}
                  max={20}
                  value={suggestionCount}
                  onChange={(e) => setSuggestionCount(Number(e.target.value))}
                />
              </div>
              <button
                className="btn btn-primary"
                style={{ marginTop: 20 }}
                onClick={handleGetSuggestions}
                disabled={suggestMutation.isPending}
              >
                {suggestMutation.isPending ? 'Loading…' : '✦ Get Suggestions'}
              </button>
            </div>
          </div>

          {suggestMutation.isPending && <LoadingState message="Getting AI suggestions…" />}

          {suggestMutation.data && (
            <div className="suggestion-list">
              {suggestMutation.data.map((s) => (
                <div key={s.symbol} className="suggestion-card">
                  <div className="suggestion-info">
                    <div>
                      <span className="suggestion-symbol">{s.symbol}</span>
                      <span className="suggestion-exchange">{s.exchange}</span>
                    </div>
                    <div className="suggestion-rationale">{s.rationale}</div>
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleAddSuggestion(s)}
                    disabled={addFromSuggestion.isPending}
                  >
                    + Add
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
