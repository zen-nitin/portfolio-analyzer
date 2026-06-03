# Portfolio Analyzer

A personal dashboard for your Zerodha portfolio. It shows:

- **Total amount invested** to date and **current value**
- **XIRR** (true annualised return across all your cashflows)
- **Current holdings** with a colour-coded **status** (strong gain → strong loss)
- Per-stock **stats, performance, and price history** (PE, market cap, 52-wk
  range, 1M/6M/1Y/5Y returns, history chart)
- A **watchlist** (stored locally — Kite doesn't expose watchlists via API)
- **AI-powered** watchlist suggestions, buy/sell/hold recommendations, and
  per-stock analysis (the AI is fed real market stats, not just its training data)

It's a local, single-user tool: a FastAPI backend with a SQLite database and a
React dashboard.

**No Zerodha API subscription required.** The default flow uses an imported
**Zerodha Console tradebook CSV** for your holdings, cost basis, and lifetime
cashflows, and **Yahoo Finance** (free) for live prices and stock stats. A Kite
Connect integration is still available as an optional path if you want one-click
live sync. It's built to grow — adding a second account, a mutual-fund provider,
or a paid market-data source later is a small, contained change (see
[Architecture](#architecture)).

## Repo layout

```
portfolio-analyzer/
├── backend/    FastAPI + SQLite + Kite Connect + pluggable AI providers
├── frontend/   React + Vite + TypeScript dashboard
├── CLAUDE.md   Guidance for AI assistants working in this repo
└── README.md
```

## Prerequisites

1. **Python 3.11+** and **Node.js 18+**.
2. **Your Zerodha tradebook CSV.** Download it from **Zerodha Console → Reports
   → Tradebook** (export to CSV). This is how your holdings, cost basis, and
   lifetime cashflows (for XIRR) get in — no API needed. Live prices come from
   Yahoo Finance, which needs no key.
   - *(Optional)* If you'd rather have one-click live sync, you can create a
     **Kite Connect app** at <https://developers.kite.trade> for an API key +
     secret. Kite Connect is a paid API (~₹2000/month). This is entirely
     optional — skip it to run for free.
3. **An AI API key** for the insights features:
   - **OpenAI** (default): a key from <https://platform.openai.com> →
     *API keys*.
     ⚠️ **A ChatGPT Plus/Pro subscription is _not_ API access.** The app calls
     the OpenAI API, which is billed separately (pay-as-you-go) and needs a
     `platform.openai.com` key. Your ChatGPT subscription will not work here.
   - **or Claude** (alternative): a key from <https://console.anthropic.com>.
   - The provider is pluggable — switch with one env var, no code changes. If
     you don't configure a key, everything works except the AI features, which
     return a friendly "not configured" message.

## Setup & run

### 1. Backend (port 8000)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then edit .env (see below)
uvicorn app.main:app --reload --port 8000
```
The database and tables are created automatically on first run. Interactive API
docs: <http://localhost:8000/docs>.

Edit `.env`:
```ini
AI_PROVIDER=openai            # or "claude"
OPENAI_API_KEY=sk-...         # from platform.openai.com (NOT your ChatGPT login)
# ANTHROPIC_API_KEY=sk-ant-...  # if AI_PROVIDER=claude
```
Kite API keys are **not** set here — you add them per account in the UI.

### 2. Frontend (port 5173)
```bash
cd frontend
npm install
npm run dev
```
Open <http://localhost:5173>. The dev server proxies `/api` to the backend.

## First-time usage (no-Kite default flow)

1. Go to **Accounts** and add an account — just a label is needed (it defaults
   to a `manual`, no-broker account; Kite API fields are tucked under an
   optional "Advanced" disclosure).
2. **Import your tradebook CSV** (the prominent action on the Accounts page).
   This creates your transaction history.
3. Click **Sync** — this derives your holdings from the imported trades
   (net quantity + weighted-average cost) and fetches live prices from Yahoo
   Finance. Use **Refresh prices** anytime to re-pull just the prices.
4. Explore **Dashboard** (invested, current value, XIRR), **Holdings**,
   **Watchlist**, **Insights**, and click any symbol to open its **Stock**
   page (stats, performance, price chart).

*Optional Kite path:* if you added Kite credentials under "Advanced", use
**Connect to Zerodha** to log in (tokens expire daily, so you reconnect each
day) and **Sync** will pull holdings live from the broker instead.

## Architecture

Three pluggable interfaces keep the app future-ready:

- **Brokers** (`backend/app/brokers/`): a `BrokerConnector` base class with a
  Zerodha implementation and a registry. The default `manual` account uses no
  broker at all. Add a broker by subclassing, registering it, and creating an
  account row — nothing else changes. Credentials are stored per account.
- **AI providers** (`backend/app/ai/`): an `AIProvider` base class with OpenAI
  and Claude implementations, selected by the `AI_PROVIDER` env var.
- **Market data** (`backend/app/market/`): a `MarketDataProvider` base class
  with a Yahoo Finance (`yfinance`) implementation, selected by
  `MARKET_DATA_PROVIDER`. Swap in a paid provider (Twelve Data, EODHD, …) later
  without touching call sites.

XIRR is computed from your `Transaction` cashflows plus current holdings value,
using a dependency-free Newton-Raphson solver. See
[CLAUDE.md](./CLAUDE.md) for the full architecture, the API contract, and
development conventions.

## Testing

```bash
cd backend && pytest          # 107 tests (XIRR, status classifier, holdings
                              # derivation, market routes, API routes)
cd frontend && npm run build  # TypeScript typecheck + production build
```

## Notes

- This is a **local single-user** tool. Broker secrets and access tokens (only
  if you use the optional Kite path) are stored in the local SQLite DB for
  convenience; `.env` and `*.db` are gitignored. Don't deploy it as-is to a
  shared/multi-user environment without adding proper auth and secret management.
- **Market data caveat:** Yahoo Finance via `yfinance` is free but *unofficial*
  and can break or rate-limit without notice. It's fine for a personal tool; if
  you want guaranteed reliability, swap in a paid `MarketDataProvider` (the
  abstraction is built for exactly this) and set `MARKET_DATA_PROVIDER`.
