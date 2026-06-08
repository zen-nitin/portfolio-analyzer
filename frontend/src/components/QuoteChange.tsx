import type { MarketQuote } from '../api/types'
import { formatINR, signClass } from '../utils/format'

interface Props {
  quote?: MarketQuote | null
  loading?: boolean
  align?: 'left' | 'right'
}

/**
 * Compact price + day-movement display used in watchlist rows, the dashboard
 * watchlist widget, and the stock-detail header. Renders a muted placeholder
 * while loading or when no quote is available (e.g. Yahoo lacked data).
 */
export default function QuoteChange({ quote, loading, align = 'right' }: Props) {
  if (loading) {
    return <span className="quote-muted" style={{ display: 'block', textAlign: align }}>…</span>
  }
  if (!quote) {
    return <span className="quote-muted" style={{ display: 'block', textAlign: align }}>—</span>
  }

  const cls = signClass(quote.day_change_pct)
  const sign = quote.day_change_pct > 0 ? '+' : ''
  return (
    <div style={{ textAlign: align }}>
      <div className="quote-price">{formatINR(quote.last_price)}</div>
      <div className={`quote-delta ${cls}`}>
        {sign}
        {formatINR(quote.day_change)} ({sign}
        {quote.day_change_pct.toFixed(2)}%)
      </div>
    </div>
  )
}
