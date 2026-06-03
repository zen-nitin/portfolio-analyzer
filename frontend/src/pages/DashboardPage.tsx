import { useAccount } from '../context/AccountContext'
import { usePortfolioSummary, useHoldings } from '../hooks/usePortfolio'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import { formatINR, formatINRCompact, formatPct, formatXIRR, signClass } from '../utils/format'
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

const PIE_COLORS = [
  '#6c8ef5', '#4ade80', '#f59e0b', '#f87171', '#818cf8',
  '#34d399', '#fb923c', '#a78bfa', '#22d3ee', '#e879f9',
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

export default function DashboardPage() {
  const { selectedAccountId } = useAccount()
  const summaryQ = usePortfolioSummary(selectedAccountId)
  const holdingsQ = useHoldings(selectedAccountId)

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
            <div className="stat-label">P&amp;L</div>
            <div className={`stat-value ${signClass(summary.pnl)}`}>
              {formatINR(summary.pnl)}
            </div>
            <div className={`stat-sub ${signClass(summary.pnl_pct)}`}>
              {formatPct(summary.pnl_pct)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">XIRR</div>
            <div className={`stat-value ${summary.xirr !== null ? signClass(summary.xirr) : 'neutral'}`}>
              {formatXIRR(summary.xirr)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Day Change</div>
            <div className={`stat-value ${signClass(summary.day_change)}`}>
              {formatINR(summary.day_change)}
            </div>
          </div>
        </div>
      )}

      {holdingsQ.isLoading && <LoadingState message="Loading holdings charts…" />}

      {holdings.length > 0 && (
        <div className="two-col">
          {/* Allocation Pie */}
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

          {/* P&L Bar */}
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
        </div>
      )}

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
