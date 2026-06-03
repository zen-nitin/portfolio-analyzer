import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getStockStats,
  getStockHistory,
  getStockPerformance,
  getMarketProviders,
  refreshAccountPrices,
} from '../api/endpoints'

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
