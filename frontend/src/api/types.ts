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
  api_key?: string
  api_secret?: string
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

// Market / stock data types
export interface MarketQuote {
  symbol: string
  exchange: string
  last_price: number
  previous_close: number
  day_change: number
  day_change_pct: number
  currency: string
}

export interface StockStats {
  symbol: string
  exchange: string
  name: string | null
  last_price: number | null
  market_cap: number | null
  pe_ratio: number | null
  pb_ratio: number | null
  eps: number | null
  dividend_yield: number | null
  week52_high: number | null
  week52_low: number | null
  beta: number | null
  volume: number | null
  avg_volume: number | null
  day_high: number | null
  day_low: number | null
  sector: string | null
  industry: string | null
}

export interface StockHistoryPoint {
  date: string
  close: number
  volume: number
}

export interface StockHistory {
  symbol: string
  exchange: string
  period: string
  interval: string
  points: StockHistoryPoint[]
}

export interface StockPerformance {
  symbol: string
  exchange: string
  returns: {
    '1m': number | null
    '6m': number | null
    '1y': number | null
    '5y': number | null
  }
}

export interface MarketProvider {
  name: string
  active: boolean
  configured: boolean
}

export interface RefreshPricesResult {
  prices_refreshed: number
}
