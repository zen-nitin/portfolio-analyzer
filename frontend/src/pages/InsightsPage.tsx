import { useState } from 'react'
import { useRecommendation, useAnalysis, useAIProviders } from '../hooks/useInsights'
import { useHoldings } from '../hooks/usePortfolio'
import { useWatchlist } from '../hooks/useWatchlist'
import { useAccount } from '../context/AccountContext'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import { ActionBadge } from '../components/ui/StatusBadge'
import { ApiError } from '../api/client'
import type { Analysis } from '../api/types'

const SKIP_FIELDS = new Set(['symbol', 'summary'])

function renderAnalysisField(_key: string, val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'number') return val.toString()
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'string') return val
  return JSON.stringify(val)
}

function AnalysisExtraFields({ analysis }: { analysis: Analysis }) {
  const extras = Object.entries(analysis).filter(([k]) => !SKIP_FIELDS.has(k))
  if (!extras.length) return null
  return (
    <div className="analysis-fields">
      {extras.map(([k, v]) => (
        <div key={k} className="analysis-field">
          <div className="analysis-field-key">{k.replace(/_/g, ' ')}</div>
          <div className="analysis-field-val">{renderAnalysisField(k, v)}</div>
        </div>
      ))}
    </div>
  )
}

export default function InsightsPage() {
  const { selectedAccountId } = useAccount()
  const [symbol, setSymbol] = useState('')
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)

  const providersQ = useAIProviders()
  const holdingsQ = useHoldings(selectedAccountId)
  const watchlistQ = useWatchlist()
  const recMutation = useRecommendation()
  const analysisQ = useAnalysis(activeSymbol)

  const holdingSymbols = holdingsQ.data?.map((h) => h.symbol) ?? []
  const watchlistSymbols = watchlistQ.data?.map((w) => w.symbol) ?? []
  const allSymbols = Array.from(new Set([...holdingSymbols, ...watchlistSymbols])).sort()

  const noAI =
    (providersQ.data && !providersQ.data.some((p) => p.active && p.configured)) ||
    (recMutation.isError && recMutation.error instanceof ApiError && recMutation.error.status === 503) ||
    (analysisQ.isError && analysisQ.error instanceof ApiError && analysisQ.error.status === 503)

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    setActiveSymbol(sym)
    await recMutation.mutateAsync(sym)
  }

  function selectSymbol(sym: string) {
    setSymbol(sym)
  }

  const rec = recMutation.data
  const analysis = analysisQ.data

  return (
    <div>
      <div className="page-header">
        <h1>AI Insights</h1>
        {providersQ.data && (
          <div style={{ display: 'flex', gap: 8 }}>
            {providersQ.data.map((p) => (
              <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: p.active && p.configured ? 'var(--positive)' : 'var(--flat)',
                    display: 'inline-block',
                  }}
                />
                {p.name}
              </div>
            ))}
          </div>
        )}
      </div>

      {noAI && (
        <div className="ai-unconfigured" style={{ marginBottom: 20 }}>
          <span>⚠</span>
          <span>AI provider not configured or unavailable. Go to <em>Accounts</em> to add an API key.</span>
        </div>
      )}

      {/* Symbol picker */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">Analyze a Symbol</div>
        <form onSubmit={handleAnalyze} style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
          <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
            <label className="form-label">Symbol</label>
            <input
              className="form-input"
              placeholder="e.g. RELIANCE"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={recMutation.isPending || !symbol.trim()}
          >
            {recMutation.isPending ? 'Analyzing…' : '✦ Analyze'}
          </button>
        </form>

        {allSymbols.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="form-label" style={{ marginBottom: 8 }}>Quick pick from portfolio / watchlist</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {allSymbols.map((sym) => (
                <button
                  key={sym}
                  className={`btn btn-secondary btn-sm ${symbol === sym ? 'active' : ''}`}
                  style={symbol === sym ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : {}}
                  onClick={() => selectSymbol(sym)}
                  type="button"
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {recMutation.isPending && <LoadingState message="Getting recommendation…" />}
      {recMutation.isError && !noAI && <ErrorState error={recMutation.error} context="Recommendation" />}

      {rec && (
        <div className="insight-panel">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{rec.symbol}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>AI Recommendation</div>
            </div>
            <ActionBadge action={rec.action} />
            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Confidence</div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{Math.round(rec.confidence * 100)}%</div>
            </div>
          </div>

          <div className="confidence-bar">
            <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 60 }}>Confidence</span>
            <div className="confidence-track">
              <div
                className="confidence-fill"
                style={{
                  width: `${rec.confidence * 100}%`,
                  background:
                    rec.action === 'BUY'
                      ? 'var(--positive)'
                      : rec.action === 'SELL'
                        ? 'var(--negative)'
                        : 'var(--warning)',
                }}
              />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{Math.round(rec.confidence * 100)}%</span>
          </div>

          <div style={{ marginTop: 16 }}>
            <div className="card-title">Rationale</div>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{rec.rationale}</p>
          </div>
        </div>
      )}

      {/* Deep analysis */}
      {activeSymbol && (
        <div className="insight-panel">
          <h3>Deep Analysis — {activeSymbol}</h3>
          {analysisQ.isLoading && <LoadingState message="Loading analysis…" />}
          {analysisQ.isError && !noAI && <ErrorState error={analysisQ.error} context="Analysis" />}
          {analysis && (
            <>
              <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)', marginBottom: 12 }}>
                {analysis.summary}
              </p>
              <AnalysisExtraFields analysis={analysis} />
            </>
          )}
        </div>
      )}
    </div>
  )
}
