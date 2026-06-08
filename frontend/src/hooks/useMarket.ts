import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getStockStats,
  getStockHistory,
  getStockPerformance,
  getMarketProviders,
  getMarketQuotes,
  refreshAccountPrices,
} from '../api/endpoints'
import type { MarketQuote } from '../api/types'

/** Live quote for a single symbol (used in the stock-detail header). */
export function useStockQuote(symbol: string | null, exchange = 'NSE') {
  return useQuery({
    queryKey: ['stock-quote', symbol, exchange],
    queryFn: async () => {
      const quotes = await getMarketQuotes([symbol!], exchange)
      return quotes[0] ?? null
    },
    enabled: !!symbol,
    refetchInterval: 60_000,
  })
}

/**
 * Batch quotes for a watchlist (or any list of symbols across exchanges).
 * Groups by exchange, fetches one batch per exchange, and returns a map
 * keyed by `SYMBOL:EXCHANGE`. Individual symbol failures are skipped by the
 * backend, so missing keys simply render as "—".
 */
export function useWatchlistQuotes(items: { symbol: string; exchange: string }[] | undefined) {
  const pairs = (items ?? [])
    .map((i) => `${i.symbol.toUpperCase()}:${i.exchange.toUpperCase()}`)
    .sort()
  return useQuery({
    queryKey: ['watchlist-quotes', pairs],
    enabled: pairs.length > 0,
    refetchInterval: 60_000,
    queryFn: async () => {
      const byExchange = new Map<string, string[]>()
      for (const pair of pairs) {
        const [sym, exch] = pair.split(':')
        const list = byExchange.get(exch) ?? []
        list.push(sym)
        byExchange.set(exch, list)
      }
      const batches = await Promise.all(
        [...byExchange.entries()].map(([exch, syms]) => getMarketQuotes(syms, exch)),
      )
      const map: Record<string, MarketQuote> = {}
      for (const batch of batches) {
        for (const q of batch) {
          map[`${q.symbol.toUpperCase()}:${q.exchange.toUpperCase()}`] = q
        }
      }
      return map
    },
  })
}

export function useStockStats(symbol: string | null, exchange = 'NSE') {
  return useQuery({
    queryKey: ['stock-stats', symbol, exchange],
    queryFn: () => getStockStats(symbol!, exchange),
    enabled: !!symbol,
  })
}

export function useStockHistory(symbol: string | null, period = '1y', exchange = 'NSE') {
  return useQuery({
    queryKey: ['stock-history', symbol, period, exchange],
    queryFn: () => getStockHistory(symbol!, period, '1d', exchange),
    enabled: !!symbol,
  })
}

export function useStockPerformance(symbol: string | null, exchange = 'NSE') {
  return useQuery({
    queryKey: ['stock-performance', symbol, exchange],
    queryFn: () => getStockPerformance(symbol!, exchange),
    enabled: !!symbol,
  })
}

export function useMarketProviders() {
  return useQuery({
    queryKey: ['market-providers'],
    queryFn: getMarketProviders,
  })
}

export function useRefreshPrices() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => refreshAccountPrices(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    },
  })
}
