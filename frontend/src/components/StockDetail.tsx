import { useState } from 'react'
import {
  useStockStats,
  useStockHistory,
  useStockPerformance,
  useStockQuote,
} from '../hooks/useMarket'
import LoadingState from './ui/LoadingState'
import ErrorState from './ui/ErrorState'
import AiAnalysisButton from './AiAnalysisButton'
import { formatINR, formatNumber, signClass } from '../utils/format'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

// Period selector: label → API period value
const PERIODS: { label: string; value: string }[] = [
  { label: '1M', value: '1mo' },
  { label: '6M', value: '6mo' },
  { label: '1Y', value: '1y' },
  { label: '5Y', value: '5y' },
]

// Performance period keys (as they come from the API)
const PERF_PERIODS: { key: '1m' | '6m' | '1y' | '5y'; label: string }[] = [
  { key: '1m', label: '1M' },
  { key: '6m', label: '6M' },
  { key: '1y', label: '1Y' },
  { key: '5y', label: '5Y' },
]

function formatMarketCap(value: number | null): string {
  if (value === null || value === undefined) return '—'
  // Convert to Crores (1 Cr = 10M)
  const cr = value / 1e7
  if (cr >= 1e5) return `₹${(cr / 1e5).toFixed(2)} L Cr`
  if (cr >= 1e3) return `₹${(cr / 1e3).toFixed(2)} K Cr`
  return `₹${cr.toFixed(2)} Cr`
}

function formatVolume(value: number | null): string {
  if (value === null || value === undefined) return '—'
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)} L`
  if (value >= 1e3) return `${(value / 1e3).toFixed(2)} K`
  return formatNumber(value, 0)
}

function formatStat(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return '—'
  return formatNumber(value, decimals)
}

function formatDividendYield(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(value, 2)}%`
}

interface ChartTooltipPayload {
  value: number
  payload: { date: string; close: number }
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: ChartTooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '10px 14px',
        fontSize: 13,
      }}
    >
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{d.date}</div>
      <strong>{formatINR(d.close)}</strong>
    </div>
  )
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}

interface Props {
  symbol: string
  exchange: string
}

/**
 * Full stock detail view (header, period returns, price-history chart, key
 * stats, 52-week range). Rendered both on the standalone /stock/:symbol page
 * and inside the global stock popup (StockModalProvider).
 */
export default function StockDetail({ symbol, exchange }: Props) {
  const [period, setPeriod] = useState('1y')

  const statsQ = useStockStats(symbol, exchange)
  const historyQ = useStockHistory(symbol, period, exchange)
  const perfQ = useStockPerformance(symbol, exchange)
  const quoteQ = useStockQuote(symbol, exchange)

  const stats = statsQ.data
  const history = historyQ.data
  const perf = perfQ.data
  const quote = quoteQ.data

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div>
          {statsQ.isLoading ? (
            <div style={{ fontSize: 22, fontWeight: 700 }}>{symbol}</div>
          ) : (
            <>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                {stats?.name ?? symbol}
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 500,
                    color: 'var(--text-muted)',
                    marginLeft: 10,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {symbol} · {exchange}
                </span>
              </div>
              {stats?.last_price !== null && stats?.last_price !== undefined && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 6 }}>
                  <span
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {formatINR(stats.last_price)}
                  </span>
                  {quote && (
                    <span
                      className={`${signClass(quote.day_change_pct)}`}
                      style={{ fontSize: 15, fontWeight: 600, fontFamily: 'var(--font-mono)' }}
                    >
                      {quote.day_change_pct > 0 ? '+' : ''}
                      {formatINR(quote.day_change)} ({quote.day_change_pct > 0 ? '+' : ''}
                      {quote.day_change_pct.toFixed(2)}%)
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
        <AiAnalysisButton
          symbol={symbol}
          exchange={exchange}
          stats={stats}
          perf={perf}
        />
      </div>

      {statsQ.isError && <ErrorState error={statsQ.error} context="Stock Stats" />}

      {/* Performance chips */}
      {(perfQ.isLoading || perf) && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-title">Period Returns</div>
          {perfQ.isLoading && <LoadingState message="Loading performance…" />}
          {perfQ.isError && <ErrorState error={perfQ.error} context="Performance" />}
          {perf && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {PERF_PERIODS.map(({ key, label }) => {
                const val = perf.returns[key]
                const cls = val === null ? 'neutral' : val > 0 ? 'positive' : val < 0 ? 'negative' : 'neutral'
                return (
                  <div
                    key={key}
                    style={{
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '10px 18px',
                      textAlign: 'center',
                      minWidth: 80,
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
                      {label}
                    </div>
                    <div className={`${cls}`} style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {val === null
                        ? '—'
                        : `${val > 0 ? '+' : ''}${(val * 100).toFixed(2)}%`}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Price history chart */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Price History</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {PERIODS.map((p) => (
              <button
                key={p.value}
                className={`btn btn-sm ${period === p.value ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setPeriod(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {historyQ.isLoading && <LoadingState message="Loading price history…" />}
        {historyQ.isError && <ErrorState error={historyQ.error} context="Price History" />}
        {history && history.points.length > 0 && (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={history.points} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <defs>
                <linearGradient id="stockGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                interval="preserveStartEnd"
                minTickGap={40}
              />
              <YAxis
                tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                tickFormatter={(v: number) => `₹${formatNumber(v, 0)}`}
                domain={['auto', 'auto']}
                width={70}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="close"
                stroke="var(--accent)"
                strokeWidth={2}
                fill="url(#stockGradient)"
                dot={false}
                activeDot={{ r: 4, fill: 'var(--accent)' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
        {history && history.points.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
            No price history available for this period.
          </div>
        )}
      </div>

      {/* Stats grid */}
      {statsQ.isLoading && <LoadingState message="Loading stock stats…" />}
      {stats && (
        <div className="card">
          <div className="card-title">Key Statistics</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 12,
            }}
          >
            {[
              { label: 'Market Cap', value: formatMarketCap(stats.market_cap) },
              { label: 'P/E Ratio', value: formatStat(stats.pe_ratio) },
              { label: 'P/B Ratio', value: formatStat(stats.pb_ratio) },
              { label: 'EPS', value: stats.eps !== null ? formatINR(stats.eps) : '—' },
              { label: 'Dividend Yield', value: formatDividendYield(stats.dividend_yield) },
              { label: '52W High', value: stats.week52_high !== null ? formatINR(stats.week52_high) : '—' },
              { label: '52W Low', value: stats.week52_low !== null ? formatINR(stats.week52_low) : '—' },
              { label: 'Beta', value: formatStat(stats.beta) },
              { label: 'Volume', value: formatVolume(stats.volume) },
              { label: 'Avg Volume', value: formatVolume(stats.avg_volume) },
              { label: 'Day High', value: stats.day_high !== null ? formatINR(stats.day_high) : '—' },
              { label: 'Day Low', value: stats.day_low !== null ? formatINR(stats.day_low) : '—' },
              { label: 'Sector', value: stats.sector ?? '—' },
              { label: 'Industry', value: stats.industry ?? '—' },
            ].map(({ label, value }) => (
              <div key={label} className="analysis-field">
                <div className="analysis-field-key">{label}</div>
                <div
                  className="analysis-field-val"
                  style={{ fontFamily: typeof value === 'string' && value.startsWith('₹') ? 'var(--font-mono)' : undefined }}
                >
                  {value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 52-week range visual */}
      {stats && stats.week52_low !== null && stats.week52_high !== null && stats.last_price !== null && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">52-Week Range</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 80 }}>
              {formatINR(stats.week52_low)}
            </span>
            <div
              style={{
                flex: 1,
                height: 8,
                background: 'var(--border)',
                borderRadius: 99,
                position: 'relative',
              }}
            >
              {(() => {
                const low = stats.week52_low!
                const high = stats.week52_high!
                const cur = stats.last_price!
                const pct = ((cur - low) / (high - low)) * 100
                const clamped = Math.max(0, Math.min(100, pct))
                const cls = signClass(pct - 50)
                return (
                  <>
                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        height: '100%',
                        width: `${clamped}%`,
                        background: cls === 'positive' ? 'var(--positive)' : cls === 'negative' ? 'var(--negative)' : 'var(--neutral)',
                        borderRadius: 99,
                      }}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        top: '50%',
                        left: `${clamped}%`,
                        transform: 'translate(-50%, -50%)',
                        width: 14,
                        height: 14,
                        borderRadius: '50%',
                        background: 'var(--accent)',
                        border: '2px solid var(--bg-card)',
                      }}
                    />
                  </>
                )
              })()}
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 80, textAlign: 'right' }}>
              {formatINR(stats.week52_high)}
            </span>
          </div>
          <div style={{ textAlign: 'center', marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
            Current: {formatINR(stats.last_price)}
          </div>
        </div>
      )}
    </div>
  )
}
