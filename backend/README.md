# Portfolio Analyzer – Backend

FastAPI service (Python 3.11+) connecting to Zerodha Kite Connect, computing
portfolio metrics, managing a watchlist, and exposing AI-powered insights.

## Quick start

```bash
cd backend

# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env – at minimum set OPENAI_API_KEY or ANTHROPIC_API_KEY

# 4. Run the development server (tables are created on startup)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now available at http://localhost:8000.
Interactive docs: http://localhost:8000/docs

## Running tests

```bash
pytest -v
```

## Adding a Zerodha account

1. Create a Zerodha Kite Connect developer app at
   https://developers.kite.trade and note the **api_key** and **api_secret**.
2. `POST /api/accounts` with `{"label": "My Account", "broker": "zerodha", "api_key": "...", "api_secret": "..."}`.
3. Visit the login URL from `GET /api/auth/{account_id}/login-url` and
   complete the Kite login flow.
4. After redirect, grab the `request_token` from the redirect URL and POST
   it to `POST /api/auth/{account_id}/session {"request_token": "..."}`.
5. `POST /api/accounts/{account_id}/sync` to pull holdings and positions.

Kite access tokens expire daily. Repeat steps 3-4 each trading day.

## AI providers

### OpenAI (default)

Set `AI_PROVIDER=openai` and provide a valid `OPENAI_API_KEY` from
https://platform.openai.com/api-keys.

> **Note**: A ChatGPT subscription (chat.openai.com) gives you access to the
> ChatGPT web interface but does **not** grant API access. You need a separate
> API key from platform.openai.com, which is billed per token independently
> of any ChatGPT plan.

### Anthropic / Claude

Set `AI_PROVIDER=claude` and provide a valid `ANTHROPIC_API_KEY` from
https://console.anthropic.com/api-keys.

The Claude provider uses prompt caching on the system prompt to reduce
token costs on repeated calls.

## Architecture

- **Broker abstraction** (`app/brokers/`): Add new brokers by subclassing
  `BrokerConnector` and registering in `registry.py`.
- **AI abstraction** (`app/ai/`): Add providers by subclassing `AIProvider`
  and registering in `registry.py`.
- **XIRR** (`app/services/xirr.py`): Pure Python, no scipy dependency.
  Import your Zerodha Console tradebook CSV via
  `POST /api/transactions/import` to enable accurate XIRR calculations.

## Security note

API secrets and access tokens are stored in the local SQLite database.
This is acceptable for a single-user local tool. Do not expose the backend
to the public internet without adding authentication.
