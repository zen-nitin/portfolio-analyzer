import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import StockDetail from '../components/StockDetail'

interface StockRef {
  symbol: string
  exchange: string
}

interface StockModalContextValue {
  /** Open the stock-detail popup for a symbol (defaults exchange to NSE). */
  openStock: (symbol: string, exchange?: string) => void
  closeStock: () => void
}

const StockModalContext = createContext<StockModalContextValue | null>(null)

export function useStockModal() {
  const ctx = useContext(StockModalContext)
  if (!ctx) {
    throw new Error('useStockModal must be used within a StockModalProvider')
  }
  return ctx
}

/**
 * Provides a global stock-detail popup. Any component can call
 * `useStockModal().openStock(symbol, exchange)` to open the modal; clicking the
 * backdrop, the close button, or pressing Escape dismisses it.
 */
export function StockModalProvider({ children }: { children: ReactNode }) {
  const [stock, setStock] = useState<StockRef | null>(null)

  const openStock = useCallback((symbol: string, exchange = 'NSE') => {
    setStock({ symbol: symbol.toUpperCase(), exchange: exchange.toUpperCase() })
  }, [])

  const closeStock = useCallback(() => setStock(null), [])

  // Escape to close + lock background scroll while open.
  useEffect(() => {
    if (!stock) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setStock(null)
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [stock])

  return (
    <StockModalContext.Provider value={{ openStock, closeStock }}>
      {children}
      {stock && (
        <div className="modal-overlay" onClick={closeStock}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={closeStock} aria-label="Close">
              ✕
            </button>
            <StockDetail symbol={stock.symbol} exchange={stock.exchange} />
          </div>
        </div>
      )}
    </StockModalContext.Provider>
  )
}
