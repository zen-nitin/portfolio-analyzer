import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAccount } from '../context/AccountContext'
import { useStockModal } from '../context/StockModalContext'
import { usePortfolioSummary, useHoldings, useLivePriceRefresh } from '../hooks/usePortfolio'
import { useWatchlist, useDeleteWatchlistItem } from '../hooks/useWatchlist'
import { useFreeCash, useSetFreeCash } from '../hooks/useAccounts'
import { useWatchlistQuotes } from '../hooks/useMarket'
import {
  useAIProviders,
  usePortfolioReview,
  useAskPortfolioReview,
  useApplyManualReview,
  clearReviewCache,
} from '../hooks/useInsights'
import ExternalGenerate from '../components/ExternalGenerate'
import EntryZoneControl from '../components/EntryZone'
import { getReviewPrompt } from '../api/endpoints'
import QuoteChange from '../components/QuoteChange'
import { ActionBadge } from '../components/ui/StatusBadge'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import { ApiError } from '../api/client'
import type { PortfolioRecommendation, ReviewMessage, Holding, PortfolioSummary } from '../api/types'
import { formatINR, formatINRCompact, formatNumber, formatPct, formatXIRR, signClass } from '../utils/format'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts'

// Terminal palette — amber-led with mint, blue and red, Bloomberg-style
const PIE_COLORS = [
  '#fb8b1e', '#4af6c3', '#3b9dff', '#ff433d', '#c084fc',
  '#7ee787', '#ffd33d', '#56b6c2', '#f78166', '#9aa0ff',
]

interface TooltipPayload {
  name: string
  value: number
  payload: { name: string; value: number; pct: number }
}

function PieTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 13,
    }}>
      <strong>{d.name}</strong>
      <br />
      {formatINRCompact(d.value)} ({d.pct.toFixed(1)}%)
    </div>
  )
}

interface BarTooltipPayload {
  name: string
  value: number
}

function BarTooltip({ active, payload }: { active?: boolean; payload?: BarTooltipPayload[] }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 13,
    }}>
      <strong>{payload[0].name}</strong>: {formatINR(payload[0].value)}
    </div>
  )
}

function WatchlistWidget() {
  const { openStock } = useStockModal()
  const { data: items, isLoading } = useWatchlist()
  const quotesQ = useWatchlistQuotes(items)
  const deleteMut = useDeleteWatchlistItem()

  if (isLoading || !items) return null

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>Watchlist ({items.length})</div>
        <Link to="/watchlist" style={{ fontSize: 12, color: 'var(--accent)' }}>
          Manage →
        </Link>
      </div>
      {items.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Nothing on your watchlist yet. <Link to="/watchlist" style={{ color: 'var(--accent)' }}>Add symbols →</Link>
        </div>
      ) : (
        <div className="quote-list">
          {items.map((item) => {
            const quote = quotesQ.data?.[`${item.symbol.toUpperCase()}:${item.exchange.toUpperCase()}`]
            return (
              <div key={item.id} className="wl-dash-row">
                <div className="quote-row">
                  <button
                    type="button"
                    className="quote-row-main"
                    onClick={() => openStock(item.symbol, item.exchange)}
                  >
                    <div className="quote-row-sym">
                      <span className="wl-symbol">{item.symbol}</span>
                      <span className="wl-exchange">{item.exchange}</span>
                    </div>
                    <QuoteChange quote={quote} loading={quotesQ.isLoading} />
                  </button>
                  <button
                    type="button"
                    className="wl-remove"
                    onClick={() => deleteMut.mutate(item.id)}
                    disabled={deleteMut.isPending}
                    aria-label={`Remove ${item.symbol} from watchlist`}
                    title="Remove from watchlist"
                  >
                    ×
                  </button>
                </div>
                <div style={{ padding: '0 4px 6px' }}>
                  <EntryZoneControl item={item} quote={quote} compact />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Highest-conviction first (backend already returns only BUY/SELL, no HOLD).
function sortRecommendations(recs: PortfolioRecommendation[]): PortfolioRecommendation[] {
  return [...recs].sort((a, b) => b.conviction - a.conviction)
}

function PortfolioReviewCard() {
  const { selectedAccountId } = useAccount()
  const { openStock } = useStockModal()
  const providersQ = useAIProviders()
  const [target, setTarget] = useState(75)
  const [thread, setThread] = useState<ReviewMessage[]>([])
  const [question, setQuestion] = useState('')
  const [collapsed, setCollapsed] = useState(true)

  // Only auto-run once an AI provider is actually configured (avoids a 503 call).
  const aiConfigured = (providersQ.data ?? []).some((p) => p.active && p.configured)
  const reviewQ = usePortfolioReview(selectedAccountId, target, aiConfigured)
  const askMut = useAskPortfolioReview(selectedAccountId, target)
  const applyManualReview = useApplyManualReview(selectedAccountId, target)

  const isAIUnavailable =
    (providersQ.data !== undefined && !aiConfigured) ||
    (reviewQ.error instanceof ApiError && reviewQ.error.status === 503)

  const review = reviewQ.data
  const sorted = review ? sortRecommendations(review.recommendations) : []
  const busy = reviewQ.isFetching || askMut.isPending

  function resetReview() {
    setThread([])
    setQuestion('')
    // Drop the cached result + in-flight batch id so a fresh batch is submitted.
    clearReviewCache(selectedAccountId, target)
    reviewQ.refetch()
  }

  function submitQuestion(e: React.FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || askMut.isPending) return
    const nextThread: ReviewMessage[] = [...thread, { role: 'user', content: q }]
    setThread(nextThread)
    setQuestion('')
    askMut.mutate(nextThread, {
      onSuccess: (data) =>
        setThread([...nextThread, { role: 'assistant', content: data.answer }]),
      onError: () => setThread(thread), // roll back the optimistic user bubble on failure
    })
  }

  return (
    <div className="card review-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: collapsed ? 0 : 12 }}>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          style={{ display: 'flex', alignItems: 'center', gap: 9, background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'inherit', textAlign: 'left' }}
        >
          <span
            style={{ display: 'inline-block', color: 'var(--text-muted)', fontSize: 11, lineHeight: 1, transition: 'transform 0.15s ease', transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)' }}
          >
            ▸
          </span>
          <div>
            <div className="card-title" style={{ marginBottom: 2 }}>✦ AI Suggestions</div>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
              Actionable buy/sell vs your FY goal{review ? ` · FY ${review.fy}` : ''}
            </div>
          </div>
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
            Target
            <input
              type="number"
              className="form-input"
              style={{ width: 56, padding: '4px 6px', fontSize: 13 }}
              min={1}
              max={500}
              value={target}
              onChange={(e) => setTarget(Number(e.target.value) || 0)}
            />
            %
          </label>
          <button
            className="btn btn-secondary btn-sm"
            onClick={resetReview}
            disabled={busy || !aiConfigured}
          >
            {busy ? '…' : '↻'}
          </button>
        </div>
      </div>

      {!collapsed && (
        <>
      <ExternalGenerate
        label="review"
        fetchPrompt={() => getReviewPrompt(selectedAccountId, target).then((r) => r.prompt)}
        onApply={applyManualReview}
      />

      {isAIUnavailable && (
        <div className="ai-unconfigured">
          <span>⚠</span>
          <span>AI provider not configured. Add an API key in <em>Accounts</em> to get buy/sell calls.</span>
        </div>
      )}

      {!isAIUnavailable && !reviewQ.isError && !review && (reviewQ.isFetching || reviewQ.data === null) && (
        <LoadingState message="Preparing AI suggestions (batched to cut cost — may take a few minutes)…" />
      )}

      {!isAIUnavailable && reviewQ.isError && !(reviewQ.error instanceof ApiError && reviewQ.error.status === 503) && (
        <ErrorState error={reviewQ.error} context="Portfolio Review" />
      )}

      {review && (
        <div className="review-scroll">
          {review.portfolio_commentary && (
            <p className="review-commentary">{review.portfolio_commentary}</p>
          )}

          {sorted.length > 0 ? (
            <div className="review-list">
              {sorted.map((r, i) => (
                <div key={`${r.symbol}-${r.exchange}-${r.position}-${i}`} className="review-row">
                  <ActionBadge action={r.action} />
                  <div className="review-main">
                    <div className="review-head">
                      <button
                        type="button"
                        className="link-button"
                        style={{ fontWeight: 700 }}
                        onClick={() => openStock(r.symbol, r.exchange)}
                      >
                        {r.symbol}
                      </button>
                      <span className="position-tag">{r.position === 'HELD' ? 'Held' : 'Watch'}</span>
                      <span className="review-conviction">{Math.round(r.conviction * 100)}%</span>
                    </div>
                    <div className="review-rationale">{r.rationale}</div>
                    {r.action === 'BUY' && r.entry_hint && (
                      <div style={{ fontSize: 11.5, color: 'var(--accent)', marginTop: 3 }}>
                        ◎ Entry: {r.entry_hint}
                      </div>
                    )}
                    {r.action === 'SELL' && r.exit_hint && (
                      <div style={{ fontSize: 11.5, color: 'var(--accent)', marginTop: 3 }}>
                        ◎ Exit: {r.exit_hint}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', padding: '6px 0' }}>
              No actionable moves right now — sit tight.
            </div>
          )}

          {/* Conversation: the AI's opening take, then any Q&A */}
          <div className="review-chat">
            {thread.length === 0 && review.answer && (
              <div className="chat-msg ai">{review.answer}</div>
            )}
            {thread.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role === 'user' ? 'user' : 'ai'}`}>
                {m.content}
              </div>
            ))}
            {askMut.isPending && <div className="chat-msg ai pending">Thinking…</div>}
          </div>
        </div>
      )}

      {review && (
        <form className="chat-input-row" onSubmit={submitQuestion}>
          <input
            className="form-input"
            placeholder="Ask about these — e.g. why sell LICI?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={askMut.isPending || !aiConfigured}
          />
          <button className="btn btn-primary btn-sm" type="submit" disabled={askMut.isPending || !question.trim()}>
            Ask
          </button>
        </form>
      )}
        </>
      )}
    </div>
  )
}

// Today's % change derived from absolute day P&L vs the prior close value.
function todayPct(dayChange: number, currentValue: number): number {
  const prevValue = currentValue - dayChange
  return prevValue > 0 ? (dayChange / prevValue) * 100 : 0
}

function HoldingsCard({ holdings, summary }: { holdings: Holding[]; summary: PortfolioSummary }) {
  const { openStock } = useStockModal()
  if (holdings.length === 0) return null

  const rows = [...holdings].sort(
    (a, b) => b.last_price * b.quantity - a.last_price * a.quantity,
  )
  const dayPct = todayPct(summary.day_change, summary.current_value)

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>Holdings ({holdings.length})</div>
        <div style={{ textAlign: 'right' }}>
          <span style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--label)', marginRight: 6 }}>
            Today
          </span>
          <span className={`mono ${signClass(summary.day_change)}`} style={{ fontWeight: 600, fontSize: 13 }}>
            {formatINR(summary.day_change)} ({formatPct(dayPct)})
          </span>
        </div>
      </div>
      <div className="quote-list quote-list--full">
        {rows.map((h) => {
          const value = h.last_price * h.quantity
          const hPct = todayPct(h.day_change, value)
          return (
            <button
              key={`${h.symbol}:${h.exchange}`}
              type="button"
              className="quote-row"
              onClick={() => openStock(h.symbol, h.exchange)}
            >
              <div>
                <div className="quote-row-sym">
                  <span className="wl-symbol">{h.symbol}</span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    LTP {formatINR(h.last_price)}
                  </span>
                </div>
                <div className="text-sm" style={{ marginTop: 2 }}>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {formatNumber(h.quantity, 0)} qty · avg {formatINR(h.average_price)} ·{' '}
                  </span>
                  <span className={signClass(h.pnl)}>{formatPct(h.pnl_pct)} overall</span>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="quote-price">{formatINR(value)}</div>
                <div className={`quote-delta ${signClass(h.day_change)}`}>
                  {formatINR(h.day_change)} ({formatPct(hPct)})
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// Free cash stat card. Editable inline when a single account is selected (the
// override is per-account); in "All accounts" mode it shows the aggregate
// read-only and points the user at a specific account to edit.
function FreeCashCard({ accountId, aggregate }: { accountId?: string; aggregate: number | null }) {
  const fcQ = useFreeCash(accountId ?? '')
  const setMut = useSetFreeCash()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')

  const editable = !!accountId
  // When an account is selected, prefer its own free-cash value (it carries the
  // source label); otherwise fall back to the summary's cross-account total.
  const amount = editable ? fcQ.data?.amount ?? null : aggregate
  const source = editable ? fcQ.data?.source : undefined

  function startEdit() {
    setValue(amount != null ? String(amount) : '')
    setEditing(true)
  }

  async function save() {
    const n = Number(value)
    if (!Number.isFinite(n) || !accountId) return
    await setMut.mutateAsync({ accountId, amount: n })
    setEditing(false)
  }

  return (
    <div className="stat-card">
      <div className="stat-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>Free Cash</span>
        {editable && !editing && (
          <button
            type="button"
            className="link-button"
            style={{ fontSize: 11, color: 'var(--accent)' }}
            onClick={startEdit}
          >
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            className="form-input"
            type="number"
            step="any"
            autoFocus
            style={{ flex: 1, minWidth: 0, padding: '4px 8px', fontSize: 18, fontFamily: 'var(--font-mono)' }}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') save()
              if (e.key === 'Escape') setEditing(false)
            }}
          />
          <button className="btn btn-primary btn-sm" onClick={save} disabled={setMut.isPending}>
            {setMut.isPending ? '…' : '✓'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setEditing(false)}>✕</button>
        </div>
      ) : (
        <>
          <div className="stat-value">{amount != null ? formatINR(amount) : '—'}</div>
          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 2 }}>
            {!editable
              ? 'Select an account to edit'
              : source === 'manual'
                ? 'Manual override'
                : source === 'ledger'
                  ? 'From funds ledger'
                  : 'Tap Edit to set'}
          </div>
        </>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const { selectedAccountId } = useAccount()
  const summaryQ = usePortfolioSummary(selectedAccountId)
  const holdingsQ = useHoldings(selectedAccountId)
  // Keep holdings + summary live: refresh prices and refetch every 20s.
  useLivePriceRefresh(selectedAccountId, 20_000)

  if (summaryQ.isLoading) return <LoadingState message="Loading portfolio…" />
  if (summaryQ.isError) return <ErrorState error={summaryQ.error} context="Portfolio" />

  const summary = summaryQ.data
  const holdings = holdingsQ.data ?? []

  const totalValue = summary?.current_value ?? 0

  const pieData = holdings
    .filter((h) => h.last_price * h.quantity > 0)
    .map((h) => ({
      name: h.symbol,
      value: h.last_price * h.quantity,
      pct: totalValue > 0 ? ((h.last_price * h.quantity) / totalValue) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  const barData = holdings
    .filter((h) => h.pnl !== 0)
    .sort((a, b) => b.pnl - a.pnl)
    .slice(0, 12)
    .map((h) => ({ name: h.symbol, pnl: h.pnl }))

  return (
    <div>
      {/* Summary stat cards */}
      {summary && (
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-label">Total Invested</div>
            <div className="stat-value">{formatINR(summary.total_invested)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Current Value</div>
            <div className="stat-value">{formatINR(summary.current_value)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>P&amp;L</span>
              <span className={signClass(summary.pnl_pct)}>{formatPct(summary.pnl_pct)}</span>
            </div>
            <div className={`stat-value ${signClass(summary.pnl)}`}>
              {formatINR(summary.pnl)}
            </div>
          </div>
          {/* XIRR + Personal XIRR merged into one card */}
          <div className="stat-card">
            <div className="stat-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>XIRR</span>
              <span
                className="info-icon"
                title="Trade: annualised return on invested cost. Personal: annualised return on the money you actually put in (needs a funds ledger)."
                aria-label="Trade XIRR is return on invested cost; Personal XIRR is return on money you put in"
              >
                i
              </span>
            </div>
            <div style={{ display: 'flex', gap: 24, marginTop: 2 }}>
              <div>
                <div className={`stat-value ${summary.xirr !== null ? signClass(summary.xirr) : 'neutral'}`} style={{ fontSize: 20 }}>
                  {formatXIRR(summary.xirr)}
                </div>
                <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.8px', color: 'var(--text-muted)', marginTop: 2 }}>Trade</div>
              </div>
              <div>
                <div className={`stat-value ${summary.personal_xirr !== null ? signClass(summary.personal_xirr) : 'neutral'}`} style={{ fontSize: 20 }}>
                  {formatXIRR(summary.personal_xirr)}
                </div>
                <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.8px', color: 'var(--text-muted)', marginTop: 2 }}>Personal</div>
              </div>
            </div>
          </div>
          {summary.net_deposited !== null && (
            <div className="stat-card">
              <div className="stat-label">Cash Invested</div>
              <div className="stat-value">{formatINR(summary.net_deposited)}</div>
            </div>
          )}
          <FreeCashCard accountId={selectedAccountId} aggregate={summary.free_cash} />
        </div>
      )}

      {holdingsQ.isLoading && <LoadingState message="Loading holdings charts…" />}

      {/* 2×2 grid: charts on the left, AI suggestions + watchlist on the right */}
      <div className="dashboard-grid">
        <div className="dash-col">
          {/* Holdings list with today's P&L */}
          {summary && <HoldingsCard holdings={holdings} summary={summary} />}

          {/* Allocation Pie */}
          {holdings.length > 0 && (
            <div className="card">
              <div className="card-title">Holdings Allocation</div>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              {/* Legend */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {pieData.map((d, i) => (
                  <span
                    key={d.name}
                    style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-secondary)' }}
                  >
                    <span
                      style={{ width: 8, height: 8, borderRadius: '50%', background: PIE_COLORS[i % PIE_COLORS.length], display: 'inline-block' }}
                    />
                    {d.name}
                  </span>
                ))}
              </div>
            </div>
          )}

        </div>

        <div className="dash-col">
          <PortfolioReviewCard />
          <WatchlistWidget />

          {/* P&L Bar */}
          {holdings.length > 0 && (
            <div className="card">
              <div className="card-title">P&amp;L by Holding</div>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={barData} margin={{ top: 4, right: 8, left: 0, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    angle={-40}
                    textAnchor="end"
                    interval={0}
                  />
                  <YAxis
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    tickFormatter={(v: number) => formatINRCompact(v)}
                  />
                  <Tooltip content={<BarTooltip />} />
                  <Bar
                    dataKey="pnl"
                    name="P&L"
                    radius={[4, 4, 0, 0]}
                    fill="var(--accent)"
                  >
                    {barData.map((d, i) => (
                      <Cell key={i} fill={d.pnl >= 0 ? 'var(--positive)' : 'var(--negative)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {!summaryQ.isLoading && !summary && (
        <div className="empty-state">
          <div className="empty-state-icon">◈</div>
          <p style={{ fontSize: 15, fontWeight: 600 }}>No portfolio data</p>
          <p style={{ fontSize: 13 }}>Connect a Zerodha account to get started.</p>
        </div>
      )}
    </div>
  )
}
