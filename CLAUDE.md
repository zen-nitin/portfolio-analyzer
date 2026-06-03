# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal, single-user dashboard that connects to a Zerodha account (via the
official Kite Connect API) to show total invested amount, XIRR, current
holdings and their status, and a watchlist — plus AI-powered stock analysis,
buy/sell/hold recommendations, and watchlist suggestions. It is a local tool:
SQLite for storage, secrets in `.env`, no multi-user auth.

It is a two-process app: a **Python/FastAPI backend** (`backend/`) and a
**React + Vite + TypeScript frontend** (`frontend/`). They are decoupled and
communicate only over the REST contract under `/api`.

## Commands

### Backend (`backend/`)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # runtime + dev deps from pyproject.toml
cp .env.example .env             # then fill in AI key(s)
uvicorn app.main:app --reload --port 8000   # serves on :8000, docs at /docs

pytest                           # run all 64 tests
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
npm run dev        # Vite dev server on :5173, proxies /api -> :8000
npm run build      # tsc typecheck + production build to dist/  (use this to verify TS)
npm run preview    # serve the production build
```
There is no test runner or linter configured on the frontend — `npm run build`
(which runs `tsc` first) is the typecheck/verification gate.

### Running the whole app
Start the backend on `:8000` and the frontend on `:5173` in separate terminals.
The Vite dev server proxies `/api` to the backend, so no CORS config is needed
in dev (the backend also allows `http://localhost:5173` via `CORS_ORIGINS`).

## Architecture — the two abstractions that matter

This codebase is deliberately built around **two pluggable interfaces** so that
new brokers and AI providers can be added without touching call sites. When
extending functionality, work through these — do not hardcode Zerodha or a
specific AI vendor anywhere else.

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

### 2. AI provider abstraction (`backend/app/ai/`)
- `base.py` — `AIProvider` ABC with a single `complete(system, user,
  json_schema=None)` method. With a `json_schema` it must return a parsed
  `dict` (structured output); without one, a plain `str`.
- `openai_provider.py` — **default** (`AI_PROVIDER=openai`, model `gpt-4o`),
  uses OpenAI structured JSON output.
- `claude_provider.py` — alternative (`AI_PROVIDER=claude`, model
  `claude-sonnet-4-6`), uses prompt caching on the system prompt.
- `registry.py` — `get_provider()` returns the configured provider, or `None`
  if its API key is missing. `list_providers()` reports `{name, active,
  configured}` for the `/api/ai/providers` endpoint.
- `prompts.py` — all system prompts and JSON schemas for the three AI features
  live here, not inline in the service.

**Graceful degradation is a hard rule:** if the active provider has no API key,
`get_provider()` returns `None` and AI endpoints return **HTTP 503** with a
clear message — they must never 500. The frontend renders a friendly "AI
provider not configured" banner for 503s. Preserve this behaviour.

> **Important caveat to remember and repeat to the user:** a ChatGPT
> subscription is **not** OpenAI API access. The app calls the OpenAI **API**,
> which needs a separate pay-as-you-go key from platform.openai.com. This is
> documented in `.env.example` and `config.py`.

### Data flow & services (`backend/app/services/`)
- **Models** (`app/models/`): `Account`, `Holding`, `Transaction`,
  `WatchlistItem`. `Transaction` rows are the source of truth for cashflows.
- `sync.py` — `sync_account()` pulls live holdings/positions from the broker
  and **replaces** that account's `Holding` rows; it also records today's
  positions as `Transaction`s (deduped per symbol/day).
- `import_csv.py` — imports a **Zerodha Console tradebook CSV** into
  `Transaction` rows. This is how lifetime cashflow history gets in, because the
  Kite API only exposes the current day's trades. It tolerates many header-name
  variants and dedupes.
- `xirr.py` — **dependency-free** XIRR (Newton-Raphson with a bisection
  fallback; no scipy). Convention: outflows/buys are **negative**, inflows/sells
  **positive**, and the current holdings value is appended as a final positive
  cashflow at today's date.
- `portfolio.py` — `build_summary()` (total invested, current value, P&L, XIRR,
  day change) and the holding **status classifier**.
- `insights.py` — the three AI features; calls `get_provider()` and raises 503
  when unconfigured.

### Holding status classifier (keep these thresholds in sync)
Status is derived from P&L % vs cost. **It is computed in two places** —
`schemas/holding.py` (`HoldingRead.status` computed field, what the API
returns) and `services/portfolio.py` (`holding_status()`, used in summaries).
If you change the buckets, change both. Buckets: `STRONG_GAIN` (>15%), `GAIN`
(>0.5%), `FLAT` (−0.5%…0.5%), `LOSS` (≥−15%), `STRONG_LOSS` (<−15%). The
frontend `HoldingStatus` union and `StatusBadge` colors mirror these.

### Kite session lifecycle (don't fight this)
Kite access tokens **expire daily**. The flow: `GET /api/auth/{id}/login-url`
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
  `WatchlistPage`, `InsightsPage`, `AccountsPage`.
- `hooks/` — React Query wrappers (`usePortfolio`, `useAccounts`,
  `useWatchlist`, `useInsights`); data fetching goes through these.
- `context/AccountContext.tsx` — global "All accounts / specific account"
  selector. Summary and holdings endpoints take an optional `account_id`; the
  selector is how multi-account is surfaced in the UI.
- `components/ui/` — shared `LoadingState`, `ErrorState` (503 → AI-not-
  configured banner), `EmptyState`, `StatusBadge`. Reuse these for new views.

## API contract (`/api`)
Backend routers in `app/routers/` and frontend `api/endpoints.ts` must stay in
lockstep. Endpoints: accounts CRUD + `POST /accounts/{id}/sync`; auth
`login-url`/`session`/`status`; `GET /portfolio/summary?account_id=`; `GET
/holdings?account_id=`; transactions list + `POST /transactions/import`
(multipart CSV); watchlist CRUD; insights `watchlist-suggestions`,
`recommendation`, `analysis/{symbol}`; `GET /ai/providers`; `GET /health`.
`xirr` is returned as a decimal (e.g. `0.184` = 18.4%) and may be `null`.

## Conventions
- Backend: SQLAlchemy 2.x typed models, Pydantic v2 schemas, DB sessions via
  FastAPI dependency injection. Pinned deps in `pyproject.toml`.
- Tests must not hit the network — brokers and AI providers are mocked, and DB
  tests use a temp/in-memory SQLite. New broker/AI/service logic should follow
  this (the thorough coverage to date is XIRR, the status classifier, and the
  API routes).
- Secrets stay server-side and out of git (`.env`, `*.db` are gitignored).
