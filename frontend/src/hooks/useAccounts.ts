import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAccounts, createAccount, syncAccount, getAuthStatus, getLoginUrl, createSession, addShares, getFreeCash, setFreeCash } from '../api/endpoints'
import type { AccountCreate } from '../api/types'

export function useFreeCash(accountId: string) {
  return useQuery({
    queryKey: ['free-cash', accountId],
    queryFn: () => getFreeCash(accountId),
    enabled: !!accountId,
  })
}

export function useSetFreeCash() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ accountId, amount }: { accountId: string; amount: number }) =>
      setFreeCash(accountId, amount),
    onSuccess: (_data, { accountId }) => {
      qc.invalidateQueries({ queryKey: ['free-cash', accountId] })
      qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    },
  })
}

interface AddSharesInput {
  accountId: string
  symbol: string
  exchange: string
  quantity: number
  price: number
  trade_date: string
  isin?: string | null
}

export function useAddShares() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ accountId, ...data }: AddSharesInput) => addShares(accountId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    },
  })
}

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AccountCreate) => createAccount(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useSyncAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => syncAccount(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    },
  })
}

export function useAuthStatus(id: string) {
  return useQuery({
    queryKey: ['auth-status', id],
    queryFn: () => getAuthStatus(id),
    refetchInterval: 30_000,
  })
}

export function useLoginUrl() {
  return useMutation({
    mutationFn: (id: string) => getLoginUrl(id),
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, request_token }: { id: string; request_token: string }) =>
      createSession(id, request_token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auth-status'] }),
  })
}
