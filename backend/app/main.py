"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload

The database tables are created automatically on first startup via
``init_db()``.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import accounts, auth, holdings, insights, market, portfolio, transactions, watchlist


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise DB on startup."""
    init_db()
    yield


app = FastAPI(
    title="Portfolio Analyzer API",
    description="Zerodha portfolio dashboard backend with AI-powered insights.",
    version="0.1.0",
    lifespan=lifespan,
)

# ------------------------------------------------------------------
# CORS – allow the Vite dev server (and any configured origins)
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(portfolio.router)
app.include_router(holdings.router)
app.include_router(transactions.router)
app.include_router(watchlist.router)
app.include_router(insights.router)
app.include_router(market.router)


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------
@app.get("/api/health", tags=["health"])
def health():
    """Simple liveness probe."""
    return {"status": "ok", "version": "0.1.0"}
