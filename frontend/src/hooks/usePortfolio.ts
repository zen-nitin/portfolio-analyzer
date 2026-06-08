import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getPortfolioSummary,
  getHoldings,
  getExitedHoldings,
  refreshPortfolioPrices,
} from '../api/endpoints'

export function usePortfolioSummary(accountId?: string) {
  return useQuery({
    queryKey: ['portfolio-summary', accountId],
    queryFn: () => getPortfolioSummary(accountId),
  })
}

export function useHoldings(accountId?: string) {
  return useQuery({
    queryKey: ['holdings', accountId],
    queryFn: () => getHoldings(accountId),
  })
}

/** Fully-exited (no longer held) positions derived from the trade history. */
export function useExitedHoldings(accountId?: string, enabled = true) {
  return useQuery({
    queryKey: ['holdings-exited', accountId],
    queryFn: () => getExitedHoldings(accountId),
    enabled,
  })
}

/**
 * Periodically refresh live prices server-side, then refetch holdings + summary
 * so the dashboard numbers stay current. A plain refetch wouldn't help — the
 * backend only updates prices when refresh-prices runs — so each tick refreshes
 * first, then invalidates. Errors (e.g. a transient yfinance hiccup) are
 * swallowed so the UI never flickers an error during the poll.
 */
export function useLivePriceRefresh(accountId?: string, intervalMs = 20_000) {
  const queryClient = useQueryClient()

  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      try {
        const result = await refreshPortfolioPrices(accountId)
        if (cancelled) return
        // Outside market hours the backend skips the refresh, so prices are
        // unchanged — don't churn refetches of the same data.
        if (result.market_open === false) return
        queryClient.invalidateQueries({ queryKey: ['holdings'] })
        queryClient.invalidateQueries({ queryKey: ['portfolio-summary'] })
      } catch {
        /* ignore transient refresh failures; keep the existing data on screen */
      }
    }

    const id = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [accountId, intervalMs, queryClient])
}
