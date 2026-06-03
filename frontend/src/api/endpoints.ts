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
  MarketProvider,
  MarketQuote,
  PortfolioSummary,
  Recommendation,
  RefreshPricesResult,
  StockHistory,
  StockPerformance,
  StockStats,
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

// Market data
export const getMarketQuotes = (symbols: string[], exchange = 'NSE') => {
  const qs = `symbols=${symbols.map(encodeURIComponent).join(',')}&exchange=${encodeURIComponent(exchange)}`
  return api.get<MarketQuote[]>(`/market/quote?${qs}`)
}

export const getStockStats = (symbol: string, exchange = 'NSE') =>
  api.get<StockStats>(`/market/stats/${encodeURIComponent(symbol)}?exchange=${encodeURIComponent(exchange)}`)

export const getStockHistory = (symbol: string, period = '1y', interval = '1d', exchange = 'NSE') =>
  api.get<StockHistory>(
    `/market/history/${encodeURIComponent(symbol)}?period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}&exchange=${encodeURIComponent(exchange)}`,
  )

export const getStockPerformance = (symbol: string, exchange = 'NSE') =>
  api.get<StockPerformance>(
    `/market/performance/${encodeURIComponent(symbol)}?exchange=${encodeURIComponent(exchange)}`,
  )

export const getMarketProviders = () => api.get<MarketProvider[]>('/market/providers')

export const refreshAccountPrices = (id: string) =>
  api.post<RefreshPricesResult>(`/accounts/${id}/refresh-prices`)
