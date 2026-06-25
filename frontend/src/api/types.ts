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
  // Ledger-derived "from pocket" figures (null until a funds ledger is imported)
  net_deposited: number | null
  total_withdrawn: number | null
  total_charges: number | null
  free_cash: number | null
  personal_xirr: number | null
}

// Ledger (cash account) types
export type LedgerEntryType =
  | 'deposit'
  | 'withdrawal'
  | 'charge'
  | 'trade'
  | 'dividend'
  | 'other'

export interface LedgerEntry {
  id: number
  account_id: number
  entry_date: string
  entry_type: LedgerEntryType
  debit: number
  credit: number
  amount: number
  balance: number
  particulars: string
  voucher_type: string
  created_at: string
}

export interface LedgerImportResponse {
  message: string
  imported: number
  skipped: number
  errors: string[]
  net_deposited: number
  total_deposited: number
  total_withdrawn: number
  total_charges: number
  free_cash: number
}

// Holdings types
export type HoldingStatus = 'STRONG_GAIN' | 'GAIN' | 'FLAT' | 'LOSS' | 'STRONG_LOSS'

export interface Holding {
  account_id: number
  symbol: string
  exchange: string
  isin?: string | null
  quantity: number
  average_price: number
  last_price: number
  pnl: number
  pnl_pct: number
  status: HoldingStatus
  day_change: number
}

// A fully-exited (no longer held) position, derived from the trade history.
export interface ExitedPosition {
  symbol: string
  exchange: string
  isin: string | null
  quantity: number          // lot size held just before exiting
  average_price: number     // average price held at exit
  exit_date: string | null  // YYYY-MM-DD
  realized_pnl: number
  buy_value: number
  sell_value: number
}

// Watchlist types
export interface WatchlistItem {
  id: string
  symbol: string
  exchange: string
  note: string
  // Optional buy-price range; either bound may be null.
  entry_low: number | null
  entry_high: number | null
  // Optional trade-plan notes; either field may be null.
  catalyst: string | null
  exit_when: string | null
}

export interface WatchlistCreate {
  symbol: string
  exchange: string
  note: string
  entry_low?: number | null
  entry_high?: number | null
  catalyst?: string | null
  exit_when?: string | null
}

export type SuggestionBucket = 'CORE_GROWTH' | 'TACTICAL' | 'SWAP_CANDIDATE'
export type SuggestionRisk = 'LOW' | 'MEDIUM' | 'HIGH'

export interface WatchlistSuggestion {
  symbol: string
  exchange: string
  rationale: string
  // The bucketed-bench fields (optional for resilience to older/sync shapes).
  bucket?: SuggestionBucket
  risk?: SuggestionRisk
  horizon?: string
  catalyst?: string | null
  exit_trigger?: string | null
  replaces?: string | null
}

export interface FlaggedHolding {
  symbol: string
  reason: string
}

export interface WatchlistSuggestions {
  suggestions: WatchlistSuggestion[]
  flagged_holdings?: FlaggedHolding[]
}

// Insights types. The AI features are PROMPT-ONLY — the app calls no AI model;
// these shapes describe the JSON the user pastes back from Claude/ChatGPT.
export type InsightAction = 'BUY' | 'SELL' | 'HOLD'

// Portfolio review (AI analysis of all holdings + watchlist vs an FY goal)
export interface PortfolioRecommendation {
  symbol: string
  exchange: string
  position: 'HELD' | 'WATCHLIST'
  action: InsightAction
  conviction: number
  rationale: string
  entry_hint?: string | null
  exit_hint?: string | null
}

export interface PortfolioReview {
  fy: string
  target_profit_pct: number
  answer: string
  portfolio_commentary: string
  recommendations: PortfolioRecommendation[]
}

// Transaction types
export interface Transaction {
  id: string
  symbol: string
  exchange: string
  isin?: string | null
  trade_type: string
  quantity: number
  price: number
  amount: number
  fees?: number
  trade_date: string
  account_id?: string
}

// Add/edit a single trade behind a holding. `amount` is always derived
// server-side (qty × price, 0 for a bonus), so it is never sent.
export interface TransactionCreate {
  account_id: number
  symbol: string
  exchange: string
  isin?: string | null
  trade_type: string        // buy | sell | bonus
  quantity: number
  price: number
  trade_date: string
  fees?: number
}

export type TransactionUpdate = Partial<Omit<TransactionCreate, 'account_id'>>

export interface TransactionMutationResponse {
  message: string
  transaction: Transaction
  holdings_synced: number
  prices_refreshed: number
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
  /** False when the poll was skipped because the market is closed. */
  market_open?: boolean
}
