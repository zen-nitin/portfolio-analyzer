# Portfolio Analyzer

A personal dashboard for your Zerodha account. It connects via the official
**Kite Connect API** and shows:

- **Total amount invested** to date and **current value**
- **XIRR** (true annualised return across all your cashflows)
- **Current holdings** with a colour-coded **status** (strong gain → strong loss)
- A **watchlist** (stored locally — Kite doesn't expose watchlists via API)
- **AI-powered** watchlist suggestions, buy/sell/hold recommendations, and
  per-stock analysis

It's a local, single-user tool: a FastAPI backend with a SQLite database and a
React dashboard. It's built to grow — adding a second Zerodha account or a
mutual-fund provider later is a small, contained change (see
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
2. **A Kite Connect app.** Create one at <https://developers.kite.trade> to get
   an **API key** and **API secret**. Kite Connect is a paid API (~₹2000/month)
   for personal use. Each Zerodha account you add needs its own key/secret.
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

## First-time usage

1. Go to **Accounts**, add an account (label + `zerodha` + your Kite API key &
   secret).
2. Click **Connect to Zerodha**, log in, and you'll be redirected back with a
   session. *(Kite access tokens expire daily, so you'll reconnect each day.)*
3. Click **Sync** to pull your current holdings.
4. For lifetime **XIRR**, import your full trade history: download your
   **tradebook CSV from Zerodha Console** and upload it on the Accounts page.
   (The Kite API only exposes the current day's trades, so historical cashflows
   come from this import.)
5. Explore **Dashboard**, **Holdings**, **Watchlist**, and **Insights**.

## Architecture

Two pluggable interfaces keep the app future-ready:

- **Brokers** (`backend/app/brokers/`): a `BrokerConnector` base class with a
  Zerodha implementation and a registry. Add a broker by subclassing,
  registering it, and creating an account row — nothing else changes.
  Credentials are stored per account.
- **AI providers** (`backend/app/ai/`): an `AIProvider` base class with OpenAI
  and Claude implementations, selected by the `AI_PROVIDER` env var.

XIRR is computed from your `Transaction` cashflows plus current holdings value,
using a dependency-free Newton-Raphson solver. See
[CLAUDE.md](./CLAUDE.md) for the full architecture, the API contract, and
development conventions.

## Testing

```bash
cd backend && pytest          # 64 tests (XIRR, status classifier, API routes)
cd frontend && npm run build  # TypeScript typecheck + production build
```

## Notes

- This is a **local single-user** tool. Broker secrets and access tokens are
  stored in the local SQLite DB for convenience; `.env` and `*.db` are
  gitignored. Don't deploy it as-is to a shared/multi-user environment without
  adding proper auth and secret management.
