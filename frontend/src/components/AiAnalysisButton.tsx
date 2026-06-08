import { useState } from 'react'
import type { StockStats, StockPerformance } from '../api/types'

interface Props {
  symbol: string
  exchange: string
  stats?: StockStats | null
  perf?: StockPerformance | null
}

const inr = (v: number) => `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`

/**
 * Build a self-contained analyst prompt from the stock data we already have, so
 * the external chat opens with full context (price, valuation, returns).
 */
function buildPrompt(symbol: string, exchange: string, stats?: StockStats | null, perf?: StockPerformance | null): string {
  const name = stats?.name || symbol
  const parts: string[] = [
    `Act as an equity analyst. Give a BUY / SELL / HOLD view on ${name} (${symbol}, ${exchange}) ` +
      `for an Indian retail investor — with clear rationale, key risks, and near-term catalysts. ` +
      `Use the latest news and current market context, not just past performance.`,
  ]

  const snap: string[] = []
  if (stats?.last_price != null) snap.push(`Price ${inr(stats.last_price)}`)
  if (stats?.pe_ratio != null) snap.push(`P/E ${stats.pe_ratio.toFixed(1)}`)
  if (stats?.pb_ratio != null) snap.push(`P/B ${stats.pb_ratio.toFixed(2)}`)
  if (stats?.eps != null) snap.push(`EPS ${inr(stats.eps)}`)
  if (stats?.week52_low != null && stats?.week52_high != null)
    snap.push(`52-wk ${inr(stats.week52_low)}–${inr(stats.week52_high)}`)
  if (stats?.dividend_yield != null) snap.push(`Div yield ${stats.dividend_yield.toFixed(2)}%`)
  if (stats?.sector) snap.push(`Sector ${stats.sector}`)
  if (perf?.returns) {
    const r = perf.returns
    const f = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
    snap.push(`Returns 1M ${f(r['1m'])} · 6M ${f(r['6m'])} · 1Y ${f(r['1y'])}`)
  }
  if (snap.length) parts.push(`Snapshot (as of today): ${snap.join(' · ')}.`)

  return parts.join('\n\n')
}

export default function AiAnalysisButton({ symbol, exchange, stats, perf }: Props) {
  const [open, setOpen] = useState(false)

  function openExternal(base: string) {
    const prompt = buildPrompt(symbol, exchange, stats, perf)
    window.open(`${base}${encodeURIComponent(prompt)}`, '_blank', 'noopener,noreferrer')
    setOpen(false)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        ✦ Get AI Analysis ▾
      </button>
      {open && (
        <>
          {/* click-away backdrop */}
          <div
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 40 }}
          />
          <div
            role="menu"
            style={{
              position: 'absolute',
              top: 'calc(100% + 6px)',
              right: 0,
              zIndex: 41,
              minWidth: 190,
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              boxShadow: 'var(--shadow-md)',
              padding: 4,
            }}
          >
            <button className="ai-menu-item" role="menuitem" onClick={() => openExternal('https://chatgpt.com/?q=')}>
              Open in ChatGPT ↗
            </button>
            <button className="ai-menu-item" role="menuitem" onClick={() => openExternal('https://claude.ai/new?q=')}>
              Open in Claude ↗
            </button>
          </div>
        </>
      )}
    </div>
  )
}
