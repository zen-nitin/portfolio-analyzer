import { useParams, useSearchParams } from 'react-router-dom'
import StockDetail from '../components/StockDetail'

/**
 * Standalone stock page at /stock/:symbol?exchange=. The same content is shown
 * in the global popup (StockModalProvider); this route exists for deep links
 * and browser-back navigation.
 */
export default function StockPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const [searchParams] = useSearchParams()

  const exchange = searchParams.get('exchange') ?? 'NSE'

  if (!symbol) {
    return <div className="error-state">No symbol specified.</div>
  }

  return <StockDetail symbol={symbol} exchange={exchange} />
}
