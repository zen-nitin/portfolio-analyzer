import { useQuery } from '@tanstack/react-query'
import { getPortfolioSummary, getHoldings } from '../api/endpoints'

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
