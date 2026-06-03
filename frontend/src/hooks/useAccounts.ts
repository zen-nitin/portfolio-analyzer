import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAccounts, createAccount, syncAccount, getAuthStatus, getLoginUrl, createSession } from '../api/endpoints'
import type { AccountCreate } from '../api/types'

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
