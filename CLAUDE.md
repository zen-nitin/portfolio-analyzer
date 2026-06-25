# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal, single-user dashboard for a Zerodha portfolio that shows total
invested amount, XIRR, current holdings and their status, a watchlist, and
per-stock **stats / performance / price history** — plus AI-powered portfolio
review (buy/sell calls) and watchlist suggestions. It is a
local tool: SQLite for storage, secrets in `.env`, no multi-user auth.

**The AI features are PROMPT-ONLY — the app calls no AI model and needs no AI
API key.** For the review and suggestions, the backend assembles a self-contained
prompt (your live portfolio context + a JSON schema) that you run in your own
**Claude/ChatGPT** (using your subscription). That model spins up its own
subagents, fetches live data from Yahoo Finance and researches the latest news
itself, and returns JSON — which you paste back into the app. So a Claude/ChatGPT
**subscription is exactly what you use** here; no pay-as-you-go API key is needed.

**It does not require the Zerodha Kite API.** The default ("manual") flow needs
no broker credentials at all: holdings, cost basis, and lifetime cashflows come
from an imported **Zerodha Console tradebook CSV**, and live prices + stock
stats come from **Yahoo Finance** (the `yfinance` package). The Kite Connect
path still exists (broker abstraction below) for anyone who wants one-click live
sync, but it is optional, not the happy path.

It is a two-process app: a **Python/FastAPI backend** (`backend/`) and a
**React + Vite + TypeScript frontend** (`frontend/`). They are decoupled and
communicate only over the REST contract under `/api`.

## Commands

### Backend (`backend/`)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # runtime + dev deps from pyproject.toml
cp .env.example .env             # no AI key needed (AI features are prompt-only)
uvicorn app.main:app --reload --port 9000   # serves on :9000, docs at /docs

pytest                           # run all 156 tests
pytest tests/test_xirr.py        # one file
pytest tests/test_xirr.py::test_simple_two_cashflow   # one test
pytest -k portfolio              # by keyword
```
The SQLite DB (`backend/portfolio.db`) and its tables are created
automatically on startup by `init_db()` (see `app/main.py` lifespan). There are
**no migrations** — the schema is created from the SQLAlchemy models. If you
change a model, delete `portfolio.db` (or migrate by hand) to pick it up.

### Frontend (`frontend/`)
```bash
cd frontend
npm install
npm run dev        # Vite dev server on :5173, proxies /api -> :9000
npm run build      # tsc typecheck + production build to dist/  (use this to verify TS)
npm run preview    # serve the production build
```
There is no test runner or linter configured on the frontend — `npm run build`
(which runs `tsc` first) is the typecheck/verification gate.

### Running the whole app
Start the backend on `:9000` and the frontend on `:5173` in separate terminals.
The Vite dev server proxies `/api` to the backend, so no CORS config is needed
in dev (the backend also allows `http://localhost:5173` via `CORS_ORIGINS`).

## Architecture — the two abstractions that matter

This codebase is deliberately built around **two pluggable interfaces** so that
new brokers and market-data sources can be added without touching call sites.
When extending functionality, work through these — do not hardcode Zerodha or
yfinance anywhere else. (There is no AI-provider abstraction: the AI features are
prompt-only — see below.)

### 1. Broker abstraction (`backend/app/brokers/`)
- `base.py` — `BrokerConnector` ABC. Methods: `get_login_url`,
  `generate_session(request_token)`, `get_holdings`, `get_positions`,
  `get_quote`, `get_profile`. The constructor takes `(api_key, api_secret,
  access_token)` so a connector is fully self-contained.
- `zerodha.py` — the Kite Connect implementation (uses the `kiteconnect` SDK).
- `registry.py` — `BROKER_REGISTRY` maps a broker-name string → connector
  class, and `get_connector(account)` builds the right connector from an
  `Account` DB row.

**Adding a broker** (e.g. a second Zerodha login, or a mutual-fund provider) is:
subclass `BrokerConnector`, register it in `registry.py`, and create an
`Account` row with that broker string. **Nothing else changes** — the
multi-account design is the whole point (the user intends to add more Zerodha
and MF accounts). All broker credentials live **per-account in the DB**, not in
`config.py`.

### AI insights are PROMPT-ONLY (no AI-provider abstraction)
There is **no** `app/ai/` provider abstraction, no OpenAI/Anthropic SDK call, no
API key, and no batch/web-search machinery in the app. The two AI features
(portfolio review, watchlist suggestions) work like this:
1. The backend **assembles a self-contained prompt** — `app/services/insights.py`
   builds the portfolio context (the data only the app has: holdings, cost basis,
   P&L, watchlist, free cash, XIRR) and `app/ai/prompts.py` supplies the system/
   user text + JSON schema. The two `/prompt` endpoints return `{prompt}`.
2. The **user runs that prompt in their own Claude/ChatGPT** (subscription, not
   API). The prompt instructs the model to **spin up its own subagents, fetch
   live data from Yahoo Finance, research the latest news**, and return JSON
   matching the schema.
3. The user **pastes the JSON back**; the frontend (`ExternalGenerate` +
   `useApplyManualReview` / `useWatchlistSuggestions().applyManual`) validates it,
   stores it in localStorage, and renders it.

So `app/ai/` is **just `prompts.py`** (prompt text + the two JSON schemas). The
backend does **no research and no market-data fetching for the AI features** —
the model does all of it. When changing a schema, update both `prompts.py` and
the frontend types/ingestion in lockstep. Do **not** reintroduce a server-side AI
call, an API key, or code-side research — the whole point is that Claude/ChatGPT
does the work via a pasted prompt. (See `app/services/insights.py`:
`watchlist_suggestions_prompt` / `portfolio_review_prompt`.)

### 2. Market data abstraction (`backend/app/market/`)
- `base.py` — `MarketDataProvider` ABC: `get_quote`, `get_quotes` (batch),
  `get_stats`, `get_history`, `get_performance`. This is **stock/market data**
  (about the instrument, not your account), distinct from the broker.
- `yfinance_provider.py` — **default** (`MARKET_DATA_PROVIDER=yfinance`). Uses
  Yahoo Finance via the `yfinance` package. Maps exchange → Yahoo suffix
  (`NSE`→`.NS`, `BSE`→`.BO`). yfinance is **unofficial** and can break; the
  provider is defensive and raises `RuntimeError` on hard failure, which the
  router turns into **HTTP 503** (never 500). No API key needed.
- `registry.py` — `get_market_provider()` / `list_market_providers()`, mirroring
  the AI registry (`{name, active, configured}`; yfinance is always
  `configured`).

**Adding a market-data source** (e.g. a paid Twelve Data / EODHD provider for
reliability): subclass `MarketDataProvider`, register it, set
`MARKET_DATA_PROVIDER`. Nothing at the call sites changes.

### Data flow & services (`backend/app/services/`)
- **Models** (`app/models/`): `Account`, `Holding`, `Transaction`,
  `LedgerEntry`, `WatchlistItem`. `Transaction` rows (share trades) are the
  source of truth for **trade** cashflows; `LedgerEntry` rows (the broker cash
  ledger — deposits, withdrawals, charges, settlements) are the source of truth
  for **money-from-pocket** and the personal XIRR. The two are deliberately
  separate and their cashflows are disjoint (no double counting).
  `Account.api_key`/`api_secret` are **optional** (nullable) — a `manual`
  account has none.
- `holdings_derivation.py` — `derive_holdings_from_transactions()` nets
  buys−sells **by ISIN** (falling back to symbol when ISIN is absent) into
  `Holding` rows with weighted-average cost. Netting is **not** per
  (symbol, exchange): shares are fungible across NSE/BSE in one demat and a
  ticker can be renamed (ZOMATO→ETERNAL) under a stable ISIN, so a per-exchange
  key would leave **phantom holdings** for positions whose legs span exchanges
  or a rename. The display symbol/exchange come from the most recent trade (so a
  renamed holding shows its current ticker, which is also what price lookup
  needs). This is how the **no-broker** flow builds holdings from the imported
  CSV (no Kite needed); `last_price` is left for the price refresh to fill.
- `price_refresh.py` — `refresh_prices()` fetches live quotes from the market
  provider for an account's holdings and updates `last_price`, `day_change`,
  and `pnl`. Provider failure raises (→ 503); partial updates are fine.
- `sync.py` — the **Kite** path: `sync_account()` pulls live holdings/positions
  from the broker and **replaces** that account's `Holding` rows; it also
  records today's positions as `Transaction`s (deduped per symbol/day). The
  `POST /accounts/{id}/sync` router **forks on broker**: `manual` → derive from
  transactions + refresh prices; `zerodha` → this broker sync.
- `import_csv.py` — imports a **Zerodha Console tradebook CSV** into
  `Transaction` rows (capturing **ISIN** when the export includes it — used as
  the holdings netting key). This is how lifetime cashflow history gets in,
  because the Kite API only exposes the current day's trades. It tolerates many
  header-name variants and dedupes.
- `import_ledger.py` — imports a **Zerodha Console funds/ledger CSV** into
  `LedgerEntry` rows. Classifies each row by `voucher_type` (+ particulars
  fallback): `Bank Receipts`→deposit, `Bank Payments`→withdrawal, `Journal
  Entry`→charge, `Book Voucher`→trade, `Reversal Voucher`→other; `amount` is
  stored signed (credit−debit). Tolerates header variants, dedupes on
  (account, date, particulars, debit, credit), and skips Opening/Closing
  Balance markers.
- `xirr.py` — **dependency-free** XIRR (Newton-Raphson with a bisection
  fallback; no scipy). Convention: outflows/buys are **negative**, inflows/sells
  **positive**, and the current holdings value is appended as a final positive
  cashflow at today's date.
- `portfolio.py` — `build_summary()` (total invested, current value, P&L, trade
  XIRR, day change) and the holding **status classifier**. When a ledger has
  been imported it also derives **`net_deposited`** (deposits−withdrawals =
  money from pocket), `total_withdrawn`, `total_charges`, `free_cash` (latest
  ledger balance, summed per account), and **`personal_xirr`** — XIRR on bank
  deposits/withdrawals + (holdings value + free cash) as the final flow. These
  ledger fields are `null` until a ledger is imported.
- `insights.py` — **PROMPT-ONLY**; calls no AI model and fetches no market data.
  Two builders — `watchlist_suggestions_prompt(count, holdings, watchlist)` and
  `portfolio_review_prompt(holdings, watchlist, summary, target, today)` — turn
  the portfolio context (DB-only: symbol, qty, avg cost, last-known price, P&L%,
  free cash, XIRR) plus the `prompts.py` system/user text and JSON schema into a
  single copy-paste prompt (via `_wrap_as_prompt`). The prompt tells the model to
  spin up **its own subagents**, fetch live data from **Yahoo Finance itself**,
  research the latest dated news/fundamentals per stock, and return JSON matching
  the schema. There is **no** `get_provider`, `complete`, `web_search`, batch,
  per-stock fan-out, or market-stats injection — the model does all the work.
  `current_fy_label()` (Indian FY, Apr–Mar) is the only other helper here. The
  pasted-back JSON is ingested and rendered on the frontend (`ExternalGenerate` +
  `applyManual`), not by the backend.

### Holding status classifier (keep these thresholds in sync)
Status is derived from P&L % vs cost. **It is computed in two places** —
`schemas/holding.py` (`HoldingRead.status` computed field, what the API
returns) and `services/portfolio.py` (`holding_status()`, used in summaries).
If you change the buckets, change both. Buckets: `STRONG_GAIN` (>15%), `GAIN`
(>0.5%), `FLAT` (−0.5%…0.5%), `LOSS` (≥−15%), `STRONG_LOSS` (<−15%). The
frontend `HoldingStatus` union and `StatusBadge` colors mirror these.

### Kite session lifecycle (only relevant for `zerodha` accounts)
The Kite path is **optional** — `manual` accounts never touch this. But for a
`zerodha` account, Kite access tokens **expire daily**. The flow:
`GET /api/auth/{id}/login-url`
→ user logs in at Zerodha → redirect returns a `request_token` → `POST
/api/auth/{id}/session` exchanges it for an access token stored on the
`Account`. `GET /api/auth/{id}/status` reports `connected`/`expired`/
`disconnected` by comparing the stored token's date to today. Expect to
re-auth each day; surface this rather than treating an expired token as an
error.

## Frontend structure (`frontend/src/`)
- `api/` — `client.ts` (typed fetch wrapper), `endpoints.ts` (one function per
  backend route), `types.ts` (TS mirror of the API contract). **When the
  backend contract changes, update all three.**
- `pages/` — one page per user feature: `DashboardPage`, `HoldingsPage`,
  `WatchlistPage`, `InsightsPage`, `AccountsPage`, and `StockPage`
  (`/stock/:symbol?exchange=` — stats, performance chips, history chart;
  reached by clicking any symbol or the sidebar stock-lookup box).
- `hooks/` — React Query wrappers (`usePortfolio`, `useAccounts`,
  `useWatchlist`, `useInsights`, `useMarket`); data fetching goes through these.
- `context/AccountContext.tsx` — global "All accounts / specific account"
  selector. Summary and holdings endpoints take an optional `account_id`; the
  selector is how multi-account is surfaced in the UI.
- `components/ui/` — shared `LoadingState`, `ErrorState`, `EmptyState`,
  `StatusBadge`. Reuse these for new views. The AI review/suggestions surface
  uses `components/ExternalGenerate` (copy prompt → open Claude/ChatGPT → paste
  JSON back).

## API contract (`/api`)
Backend routers in `app/routers/` and frontend `api/endpoints.ts` must stay in
lockstep. Endpoints: accounts CRUD + `POST /accounts/{id}/sync` + `POST
/accounts/{id}/refresh-prices` + `POST /accounts/{id}/add-shares` (record a
missing buy/bonus) + `POST /accounts/{id}/sell-shares` (record a sale: writes a
`sell` Transaction, re-derives holdings, returns realized P&L; rejects selling
more than held); auth `login-url`/`session`/`status` (zerodha
only); `GET /portfolio/summary?account_id=`; `POST
/portfolio/refresh-prices?account_id=` (refreshes all active accounts or one —
best-effort, never 503; powers the dashboard's 20s live refresh); `GET
/holdings?account_id=`;
transactions list + `POST /transactions/import` (multipart tradebook CSV);
`GET /ledger?account_id=` + `POST /ledger/import` (multipart funds-ledger CSV);
watchlist CRUD + `PUT /watchlist/{id}/entry-zone` (set/clear a buy-price range —
both bounds null clears it; items carry optional `entry_low`/`entry_high`, stored
in a separate `watchlist_entry_zones` table so no column migration is needed) +
`PUT /watchlist/{id}/plan` (set/clear free-text `catalyst` + `exit_when` notes —
both blank/null clears it; stored in a separate `watchlist_plans` table, same
no-migration pattern) +
`PUT /watchlist/reorder` (persist a manual top-first order via a full id list;
positions live in a separate `watchlist_positions` table — unpositioned items,
e.g. freshly added, sort to the top; the list endpoint returns this order);
insights (PROMPT-ONLY — return `{prompt}`, no AI call):
`POST /insights/watchlist-suggestions/prompt` ({count}) and
`POST /insights/portfolio-review/prompt` ({account_id, target_profit_pct}); market
`GET /market/quote?symbols=&exchange=`, `/market/stats/{symbol}`,
`/market/history/{symbol}`, `/market/performance/{symbol}`, `/market/providers`;
`GET /health`. `xirr` (trade) and `personal_xirr`
(ledger/pocket) are returned as decimals (e.g. `0.184` = 18.4%) and may be
`null`; the summary's ledger fields (`net_deposited`, `total_withdrawn`,
`total_charges`, `free_cash`, `personal_xirr`) are `null` until a funds ledger
is imported. Market endpoints return **503** when the provider fails; per-stock
fields may be `null` when Yahoo lacks them.

## Conventions
- Backend: SQLAlchemy 2.x typed models, Pydantic v2 schemas, DB sessions via
  FastAPI dependency injection. Pinned deps in `pyproject.toml`.
- Tests must not hit the network — brokers and market data are mocked, and DB
  tests use a temp/in-memory SQLite. New broker/service logic should follow
  this (the thorough coverage to date is XIRR, the status classifier, and the
  API routes).
- Secrets stay server-side and out of git (`.env`, `*.db` are gitignored).
