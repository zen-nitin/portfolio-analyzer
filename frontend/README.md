# Portfolio Analyzer — Frontend

React + Vite + TypeScript single-page dashboard for viewing your Zerodha portfolio and AI insights.

## Requirements

- Node.js 18+
- npm 9+

## Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment config
cp .env.example .env
# Edit .env to point to your backend if it's not at http://localhost:9000
```

## Running (development)

```bash
npm run dev
```

Opens at **http://localhost:5173**. The Vite dev server proxies all `/api` requests to `http://localhost:9000` (configured in `vite.config.ts`). Make sure the FastAPI backend is running on port 9000.

## Building for production

```bash
npm run build
```

Output goes to `dist/`. Serve with any static file server or `npm run preview` for a local preview.

## Environment variables

| Variable             | Default                        | Description                   |
|----------------------|--------------------------------|-------------------------------|
| `VITE_API_BASE_URL`  | `http://localhost:9000/api`    | Backend API base URL          |

## Pages

| Route       | Description                                          |
|-------------|------------------------------------------------------|
| `/`         | Dashboard — summary cards, allocation pie, P&L bar  |
| `/holdings` | Sortable holdings table with status badges           |
| `/watchlist`| Watchlist management + AI suggestions                |
| `/insights` | AI Buy/Sell/Hold recommendations + deep analysis     |
| `/accounts` | Account management, Zerodha OAuth, CSV import       |
