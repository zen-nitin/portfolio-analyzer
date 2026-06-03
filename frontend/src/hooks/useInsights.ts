import { useQuery, useMutation } from '@tanstack/react-query'
import { getRecommendation, getAnalysis, getAIProviders } from '../api/endpoints'

export function useAIProviders() {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: getAIProviders,
  })
}

export function useRecommendation() {
  return useMutation({
    mutationFn: (symbol: string) => getRecommendation(symbol),
  })
}

export function useAnalysis(symbol: string | null) {
  return useQuery({
    queryKey: ['analysis', symbol],
    queryFn: () => getAnalysis(symbol!),
    enabled: !!symbol,
  })
}
