import { api } from './client'
import type {
  Account,
  AccountCreate,
  AIProvider,
  Analysis,
  AuthStatus,
  Health,
  Holding,
  LoginUrl,
  PortfolioSummary,
  Recommendation,
  Transaction,
  WatchlistCreate,
  WatchlistItem,
  WatchlistSuggestion,
} from './types'

// Health
export const getHealth = () => api.get<Health>('/health')

// Accounts
export const getAccounts = () => api.get<Account[]>('/accounts')
export const getAccount = (id: string) => api.get<Account>(`/accounts/${id}`)
export const createAccount = (data: AccountCreate) => api.post<Account>('/accounts', data)
export const syncAccount = (id: string) => api.post<{ message: string }>(`/accounts/${id}/sync`)

// Auth
export const getLoginUrl = (id: string) => api.get<LoginUrl>(`/auth/${id}/login-url`)
export const createSession = (id: string, request_token: string) =>
  api.post<{ message: string }>(`/auth/${id}/session`, { request_token })
export const getAuthStatus = (id: string) => api.get<AuthStatus>(`/auth/${id}/status`)

// Portfolio
export const getPortfolioSummary = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.get<PortfolioSummary>(`/portfolio/summary${qs}`)
}

// Holdings
export const getHoldings = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.get<Holding[]>(`/holdings${qs}`)
}

// Transactions
export const getTransactions = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.get<Transaction[]>(`/transactions${qs}`)
}
export const importTransactions = (file: File, accountId?: string) => {
  const form = new FormData()
  form.append('file', file)
  if (accountId) form.append('account_id', accountId)
  return api.upload<{ message: string }>('/transactions/import', form)
}

// Watchlist
export const getWatchlist = () => api.get<WatchlistItem[]>('/watchlist')
export const addWatchlistItem = (data: WatchlistCreate) =>
  api.post<WatchlistItem>('/watchlist', data)
export const deleteWatchlistItem = (id: string) => api.delete<void>(`/watchlist/${id}`)

// Insights
export const getWatchlistSuggestions = (count: number) =>
  api.post<WatchlistSuggestion[]>('/insights/watchlist-suggestions', { count })
export const getRecommendation = (symbol: string) =>
  api.post<Recommendation>('/insights/recommendation', { symbol })
export const getAnalysis = (symbol: string) =>
  api.get<Analysis>(`/insights/analysis/${encodeURIComponent(symbol)}`)

// AI providers
export const getAIProviders = () => api.get<AIProvider[]>('/ai/providers')
