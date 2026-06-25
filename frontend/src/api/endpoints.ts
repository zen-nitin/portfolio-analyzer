import { api } from './client'
import type {
  Account,
  AccountCreate,
  AuthStatus,
  Health,
  Holding,
  ExitedPosition,
  LedgerEntry,
  LedgerImportResponse,
  LoginUrl,
  MarketProvider,
  MarketQuote,
  PortfolioSummary,
  RefreshPricesResult,
  StockHistory,
  StockPerformance,
  StockStats,
  Transaction,
  TransactionCreate,
  TransactionMutationResponse,
  TransactionUpdate,
  WatchlistCreate,
  WatchlistItem,
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
export const getExitedHoldings = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.get<ExitedPosition[]>(`/holdings/exited${qs}`)
}

// Refresh live prices across all active accounts (or one), then read fresh data.
export const refreshPortfolioPrices = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.post<RefreshPricesResult>(`/portfolio/refresh-prices${qs}`)
}

// Transactions
// Pass `symbol` to get just one holding's trades (its instrument group, across
// renames) — that's what the holding unit-details modal uses.
export const getTransactions = (accountId?: string, symbol?: string) => {
  const params = new URLSearchParams()
  if (accountId) params.set('account_id', accountId)
  if (symbol) params.set('symbol', symbol)
  const qs = params.toString()
  return api.get<Transaction[]>(`/transactions${qs ? `?${qs}` : ''}`)
}
// Single-trade CRUD: each mutation re-derives the account's holdings server-side.
export const createTransaction = (data: TransactionCreate) =>
  api.post<TransactionMutationResponse>('/transactions', data)
export const updateTransaction = (id: string, data: TransactionUpdate) =>
  api.put<TransactionMutationResponse>(`/transactions/${id}`, data)
export const deleteTransaction = (id: string) =>
  api.delete<{ message: string; holdings_synced: number; prices_refreshed: number }>(
    `/transactions/${id}`,
  )
export const importTransactions = (file: File, accountId?: string) => {
  const form = new FormData()
  form.append('file', file)
  if (accountId) form.append('account_id', accountId)
  return api.upload<{ message: string }>('/transactions/import', form)
}

// Ledger (cash account)
export const getLedger = (accountId?: string) => {
  const qs = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return api.get<LedgerEntry[]>(`/ledger${qs}`)
}
export const importLedger = (file: File, accountId?: string) => {
  const form = new FormData()
  form.append('file', file)
  if (accountId) form.append('account_id', accountId)
  return api.upload<LedgerImportResponse>('/ledger/import', form)
}

// Watchlist
export const getWatchlist = () => api.get<WatchlistItem[]>('/watchlist')
export const addWatchlistItem = (data: WatchlistCreate) =>
  api.post<WatchlistItem>('/watchlist', data)
export const deleteWatchlistItem = (id: string) => api.delete<void>(`/watchlist/${id}`)
// Set/clear an item's buy entry zone. Pass both null to clear.
export const setWatchlistEntryZone = (
  id: string,
  entry_low: number | null,
  entry_high: number | null,
) => api.put<WatchlistItem>(`/watchlist/${id}/entry-zone`, { entry_low, entry_high })
// Set/clear an item's trade-plan notes (catalyst + exit-when). Pass both null/blank to clear.
export const setWatchlistPlan = (
  id: string,
  catalyst: string | null,
  exit_when: string | null,
) => api.put<WatchlistItem>(`/watchlist/${id}/plan`, { catalyst, exit_when })
// Persist a new manual order (full list of ids, top first).
export const reorderWatchlist = (ids: string[]) =>
  api.put<WatchlistItem[]>('/watchlist/reorder', { ids: ids.map(Number) })

// Insights — PROMPT-ONLY. The app calls no AI model; these return an assembled
// prompt to run in Claude/ChatGPT (which researches and returns JSON the user
// pastes back). No AI API key is needed.
export const getReviewPrompt = (accountId?: string, targetProfitPct = 75) =>
  api.post<{ prompt: string }>('/insights/portfolio-review/prompt', {
    account_id: accountId ? Number(accountId) : null,
    target_profit_pct: targetProfitPct,
  })
export const getWatchlistPrompt = (count: number) =>
  api.post<{ prompt: string }>('/insights/watchlist-suggestions/prompt', { count })

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

export const addShares = (
  accountId: string,
  data: { symbol: string; exchange: string; quantity: number; price: number; trade_date: string; isin?: string | null },
) =>
  api.post<{ message: string; holdings_synced: number; prices_refreshed: number }>(
    `/accounts/${accountId}/add-shares`,
    data,
  )

// Record a sale (reduces/closes a holding, books realized P&L, re-derives holdings).
export const sellShares = (
  accountId: string,
  data: { symbol: string; exchange: string; quantity: number; price: number; trade_date: string; isin?: string | null },
) =>
  api.post<{ message: string; holdings_synced: number; prices_refreshed: number; realized_pnl: number }>(
    `/accounts/${accountId}/sell-shares`,
    data,
  )

// Free cash (manual override of the stale funds-ledger balance)
export interface FreeCash {
  account_id: number
  amount: number | null
  source: 'manual' | 'ledger' | 'none'
}
export const getFreeCash = (accountId: string) =>
  api.get<FreeCash>(`/accounts/${accountId}/free-cash`)
export const setFreeCash = (accountId: string, amount: number) =>
  api.put<FreeCash>(`/accounts/${accountId}/free-cash`, { amount })
