// Account types
export interface Account {
  id: string
  label: string
  broker: string
  api_key: string
  created_at?: string
}

export interface AccountCreate {
  label: string
  broker: string
  api_key: string
  api_secret: string
}

export interface AuthStatus {
  status: 'connected' | 'expired' | 'disconnected'
}

export interface LoginUrl {
  login_url: string
}

// Portfolio types
export interface PortfolioSummary {
  total_invested: number
  current_value: number
  pnl: number
  pnl_pct: number
  xirr: number | null
  day_change: number
}

// Holdings types
export type HoldingStatus = 'STRONG_GAIN' | 'GAIN' | 'FLAT' | 'LOSS' | 'STRONG_LOSS'

export interface Holding {
  symbol: string
  exchange: string
  quantity: number
  average_price: number
  last_price: number
  pnl: number
  pnl_pct: number
  status: HoldingStatus
  day_change: number
}

// Watchlist types
export interface WatchlistItem {
  id: string
  symbol: string
  exchange: string
  note: string
}

export interface WatchlistCreate {
  symbol: string
  exchange: string
  note: string
}

export interface WatchlistSuggestion {
  symbol: string
  exchange: string
  rationale: string
}

// Insights types
export type InsightAction = 'BUY' | 'SELL' | 'HOLD'

export interface Recommendation {
  symbol: string
  action: InsightAction
  confidence: number
  rationale: string
}

export interface Analysis {
  symbol: string
  summary: string
  [key: string]: unknown
}

// AI Provider types
export interface AIProvider {
  name: string
  active: boolean
  configured: boolean
}

// Transaction types
export interface Transaction {
  id: string
  symbol: string
  exchange: string
  trade_type: string
  quantity: number
  price: number
  trade_date: string
  account_id?: string
}

// Health
export interface Health {
  status: string
}
