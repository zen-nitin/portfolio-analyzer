import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getTransactions,
  createTransaction,
  updateTransaction,
  deleteTransaction,
} from '../api/endpoints'
import type { TransactionCreate, TransactionUpdate } from '../api/types'

/** The individual trades behind one holding (its instrument group). */
export function useHoldingTransactions(accountId?: string, symbol?: string) {
  return useQuery({
    queryKey: ['holding-transactions', accountId, symbol],
    queryFn: () => getTransactions(accountId, symbol),
    enabled: !!accountId && !!symbol,
  })
}

// Any trade change re-derives holdings server-side, so refresh everything that
// reads off holdings: the trade list, current + exited holdings, and the summary.
function useInvalidateAfterTradeChange() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['holding-transactions'] })
    qc.invalidateQueries({ queryKey: ['holdings'] })
    qc.invalidateQueries({ queryKey: ['holdings-exited'] })
    qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
  }
}

export function useCreateTransaction() {
  const invalidate = useInvalidateAfterTradeChange()
  return useMutation({
    mutationFn: (data: TransactionCreate) => createTransaction(data),
    onSuccess: invalidate,
  })
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateAfterTradeChange()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TransactionUpdate }) =>
      updateTransaction(id, data),
    onSuccess: invalidate,
  })
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateAfterTradeChange()
  return useMutation({
    mutationFn: (id: string) => deleteTransaction(id),
    onSuccess: invalidate,
  })
}
