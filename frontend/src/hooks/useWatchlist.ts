import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWatchlist,
  addWatchlistItem,
  deleteWatchlistItem,
  getWatchlistSuggestions,
} from '../api/endpoints'
import type { WatchlistCreate } from '../api/types'

export function useWatchlist() {
  return useQuery({
    queryKey: ['watchlist'],
    queryFn: getWatchlist,
  })
}

export function useAddWatchlistItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: WatchlistCreate) => addWatchlistItem(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

export function useDeleteWatchlistItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteWatchlistItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

export function useWatchlistSuggestions() {
  return useMutation({
    mutationFn: (count: number) => getWatchlistSuggestions(count),
  })
}
