"""
Integration tests for the FastAPI application.

Uses a temporary file-based SQLite database and TestClient (no real network
calls).  Broker and AI providers are mocked via the DB override.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# -----------------------------------------------------------------------
# Temporary file-based SQLite fixture
# -----------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_engine():
    """Create a temp-file SQLite engine with all tables."""
    # Import models so they register on Base.metadata
    import app.models.account      # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.ledger       # noqa: F401
    import app.models.holding      # noqa: F401
    import app.models.watchlist    # noqa: F401
    import app.models.cash         # noqa: F401

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def db_session(test_engine):
    """Provide a fresh DB session backed by the temp engine."""
    TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """TestClient with dependency override for DB session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# -----------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# -----------------------------------------------------------------------
# Accounts CRUD
# -----------------------------------------------------------------------

class TestAccounts:
    def _create_account(self, client):
        return client.post("/api/accounts", json={
            "label": "Test Account",
            "broker": "zerodha",
            "api_key": "test_key",
            "api_secret": "test_secret",
        })

    def test_list_accounts_empty(self, client):
        response = client.get("/api/accounts")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_account(self, client):
        response = self._create_account(client)
        assert response.status_code == 201
        data = response.json()
        assert data["label"] == "Test Account"
        assert data["broker"] == "zerodha"
        assert data["api_key"] == "test_key"
        assert "id" in data

    def test_get_account(self, client):
        created = self._create_account(client).json()
        response = client.get(f"/api/accounts/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_account_not_found(self, client):
        response = client.get("/api/accounts/9999")
        assert response.status_code == 404

    def test_list_accounts_after_create(self, client):
        self._create_account(client)
        response = client.get("/api/accounts")
        assert response.status_code == 200
        assert len(response.json()) == 1


# -----------------------------------------------------------------------
# Auth endpoints
# -----------------------------------------------------------------------

class TestAuth:
    def _create_account(self, client):
        return client.post("/api/accounts", json={
            "label": "Auth Test",
            "broker": "zerodha",
            "api_key": "test_key",
            "api_secret": "test_secret",
        }).json()

    def test_login_url(self, client):
        """Login URL should come from the Kite SDK (we just check it returns a string URL)."""
        account = self._create_account(client)
        response = client.get(f"/api/auth/{account['id']}/login-url")
        assert response.status_code == 200
        data = response.json()
        assert "login_url" in data
        assert isinstance(data["login_url"], str)
        assert "kite" in data["login_url"].lower() or "https" in data["login_url"].lower()

    def test_auth_status_no_token(self, client):
        account = self._create_account(client)
        response = client.get(f"/api/auth/{account['id']}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_auth_status_not_found(self, client):
        response = client.get("/api/auth/9999/status")
        assert response.status_code == 404


# -----------------------------------------------------------------------
# Portfolio summary
# -----------------------------------------------------------------------

class TestPortfolioSummary:
    def test_empty_portfolio(self, client):
        response = client.get("/api/portfolio/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_invested"] == 0.0
        assert data["current_value"] == 0.0
        assert data["pnl"] == 0.0
        assert data["xirr"] is None


# -----------------------------------------------------------------------
# Holdings
# -----------------------------------------------------------------------

class TestHoldings:
    def test_empty_holdings(self, client):
        response = client.get("/api/holdings")
        assert response.status_code == 200
        assert response.json() == []


class TestPortfolioRefreshPrices:
    def test_refresh_all_active_accounts(self, client, monkeypatch):
        import app.routers.portfolio as portfolio_router

        for label in ("A", "B"):
            client.post("/api/accounts", json={"label": label, "broker": "manual"})

        monkeypatch.setattr(portfolio_router, "is_market_open", lambda: True)
        monkeypatch.setattr(portfolio_router, "refresh_prices", lambda db, aid: 3)
        response = client.post("/api/portfolio/refresh-prices")
        assert response.status_code == 200
        assert response.json()["prices_refreshed"] == 6  # 3 per account × 2

    def test_refresh_is_best_effort_on_provider_error(self, client, monkeypatch):
        import app.routers.portfolio as portfolio_router

        client.post("/api/accounts", json={"label": "A", "broker": "manual"})

        def _boom(db, aid):
            raise RuntimeError("yfinance down")

        monkeypatch.setattr(portfolio_router, "is_market_open", lambda: True)
        monkeypatch.setattr(portfolio_router, "refresh_prices", _boom)
        response = client.post("/api/portfolio/refresh-prices")
        # Never 503/500 for the poll — it just reports what it managed (0).
        assert response.status_code == 200
        assert response.json()["prices_refreshed"] == 0

    def test_refresh_skipped_when_market_closed(self, client, monkeypatch):
        import app.routers.portfolio as portfolio_router

        client.post("/api/accounts", json={"label": "A", "broker": "manual"})

        def _should_not_run(db, aid):
            raise AssertionError("refresh_prices must not be called when market is closed")

        monkeypatch.setattr(portfolio_router, "is_market_open", lambda: False)
        monkeypatch.setattr(portfolio_router, "refresh_prices", _should_not_run)
        response = client.post("/api/portfolio/refresh-prices")
        assert response.status_code == 200
        assert response.json() == {"prices_refreshed": 0, "market_open": False}


# -----------------------------------------------------------------------
# Transactions
# -----------------------------------------------------------------------

class TestTransactions:
    def test_empty_transactions(self, client):
        response = client.get("/api/transactions")
        assert response.status_code == 200
        assert response.json() == []

    def test_import_requires_account_id(self, client):
        csv_content = b"trade_date,symbol,trade_type,quantity,price\n2023-01-01,INFY,buy,10,1500\n"
        response = client.post(
            "/api/transactions/import",
            files={"file": ("trades.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 400

    def test_import_csv(self, client, db_session):
        # Create account first
        account = client.post("/api/accounts", json={
            "label": "Tx Test",
            "broker": "zerodha",
            "api_key": "k",
            "api_secret": "s",
        }).json()

        csv_content = (
            b"trade_date,symbol,exchange,trade_type,quantity,price\n"
            b"2023-01-01,INFY,NSE,buy,10,1500\n"
            b"2023-06-01,INFY,NSE,sell,5,1700\n"
        )
        response = client.post(
            "/api/transactions/import",
            files={"file": ("trades.csv", csv_content, "text/csv")},
            data={"account_id": account["id"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2
        assert data["skipped"] == 0


# -----------------------------------------------------------------------
# Watchlist
# -----------------------------------------------------------------------

class TestWatchlist:
    def test_empty_watchlist(self, client):
        response = client.get("/api/watchlist")
        assert response.status_code == 200
        assert response.json() == []

    def test_add_item(self, client):
        response = client.post("/api/watchlist", json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "note": "Good stock",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["symbol"] == "RELIANCE"
        assert data["exchange"] == "NSE"
        assert data["note"] == "Good stock"

    def test_delete_item(self, client):
        item = client.post("/api/watchlist", json={
            "symbol": "TCS",
            "exchange": "NSE",
        }).json()
        response = client.delete(f"/api/watchlist/{item['id']}")
        assert response.status_code == 204

    def test_delete_item_not_found(self, client):
        response = client.delete("/api/watchlist/9999")
        assert response.status_code == 404

    def test_list_after_add(self, client):
        client.post("/api/watchlist", json={"symbol": "HDFC", "exchange": "NSE"})
        response = client.get("/api/watchlist")
        assert response.status_code == 200
        symbols = [item["symbol"] for item in response.json()]
        assert "HDFC" in symbols

    def test_add_with_entry_zone(self, client):
        data = client.post("/api/watchlist", json={
            "symbol": "INFY",
            "exchange": "NSE",
            "entry_low": 1500,
            "entry_high": 1450,  # given out of order — server normalizes
        }).json()
        assert data["entry_low"] == 1450
        assert data["entry_high"] == 1500

    def test_add_without_zone_has_null_bounds(self, client):
        data = client.post("/api/watchlist", json={"symbol": "WIPRO"}).json()
        assert data["entry_low"] is None
        assert data["entry_high"] is None

    def test_set_entry_zone(self, client):
        item = client.post("/api/watchlist", json={"symbol": "TCS"}).json()
        resp = client.put(f"/api/watchlist/{item['id']}/entry-zone", json={
            "entry_low": 3000,
            "entry_high": 3200,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_low"] == 3000
        assert data["entry_high"] == 3200
        # Persisted on the list read too.
        listed = next(i for i in client.get("/api/watchlist").json() if i["id"] == item["id"])
        assert listed["entry_high"] == 3200

    def test_clear_entry_zone(self, client):
        item = client.post("/api/watchlist", json={
            "symbol": "SBIN", "entry_low": 700, "entry_high": 750,
        }).json()
        resp = client.put(f"/api/watchlist/{item['id']}/entry-zone", json={
            "entry_low": None, "entry_high": None,
        })
        assert resp.status_code == 200
        assert resp.json()["entry_low"] is None
        assert resp.json()["entry_high"] is None

    def test_entry_zone_rejects_negative(self, client):
        item = client.post("/api/watchlist", json={"symbol": "ITC"}).json()
        resp = client.put(f"/api/watchlist/{item['id']}/entry-zone", json={
            "entry_low": -5,
        })
        assert resp.status_code == 400

    def test_set_entry_zone_not_found(self, client):
        resp = client.put("/api/watchlist/9999/entry-zone", json={"entry_low": 10})
        assert resp.status_code == 404

    def test_add_with_plan(self, client):
        data = client.post("/api/watchlist", json={
            "symbol": "INFY",
            "exchange": "NSE",
            "catalyst": "Q3 results beat",
            "exit_when": "Falls below 200-DMA",
        }).json()
        assert data["catalyst"] == "Q3 results beat"
        assert data["exit_when"] == "Falls below 200-DMA"

    def test_add_without_plan_has_null_fields(self, client):
        data = client.post("/api/watchlist", json={"symbol": "WIPRO"}).json()
        assert data["catalyst"] is None
        assert data["exit_when"] is None

    def test_set_plan(self, client):
        item = client.post("/api/watchlist", json={"symbol": "TCS"}).json()
        resp = client.put(f"/api/watchlist/{item['id']}/plan", json={
            "catalyst": "New order win",
            "exit_when": "Margin guidance cut",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["catalyst"] == "New order win"
        assert data["exit_when"] == "Margin guidance cut"
        # Persisted on the list read too.
        listed = next(i for i in client.get("/api/watchlist").json() if i["id"] == item["id"])
        assert listed["catalyst"] == "New order win"

    def test_set_plan_partial(self, client):
        item = client.post("/api/watchlist", json={"symbol": "ITC"}).json()
        resp = client.put(f"/api/watchlist/{item['id']}/plan", json={
            "catalyst": "Demerger value unlock",
        })
        assert resp.status_code == 200
        assert resp.json()["catalyst"] == "Demerger value unlock"
        assert resp.json()["exit_when"] is None

    def test_clear_plan(self, client):
        item = client.post("/api/watchlist", json={
            "symbol": "SBIN", "catalyst": "Credit growth", "exit_when": "NPA spike",
        }).json()
        resp = client.put(f"/api/watchlist/{item['id']}/plan", json={
            "catalyst": None, "exit_when": None,
        })
        assert resp.status_code == 200
        assert resp.json()["catalyst"] is None
        assert resp.json()["exit_when"] is None

    def test_plan_blank_strings_clear(self, client):
        item = client.post("/api/watchlist", json={
            "symbol": "HDFC", "catalyst": "Merger synergies",
        }).json()
        resp = client.put(f"/api/watchlist/{item['id']}/plan", json={
            "catalyst": "   ", "exit_when": "",
        })
        assert resp.status_code == 200
        assert resp.json()["catalyst"] is None
        assert resp.json()["exit_when"] is None

    def test_set_plan_not_found(self, client):
        resp = client.put("/api/watchlist/9999/plan", json={"catalyst": "x"})
        assert resp.status_code == 404

    def test_reorder(self, client):
        a = client.post("/api/watchlist", json={"symbol": "AAA"}).json()
        b = client.post("/api/watchlist", json={"symbol": "BBB"}).json()
        c = client.post("/api/watchlist", json={"symbol": "CCC"}).json()
        # Put them in an explicit order: B, C, A.
        resp = client.put("/api/watchlist/reorder", json={"ids": [b["id"], c["id"], a["id"]]})
        assert resp.status_code == 200
        assert [i["symbol"] for i in resp.json()] == ["BBB", "CCC", "AAA"]
        # And the order persists on a fresh GET.
        listed = client.get("/api/watchlist").json()
        assert [i["symbol"] for i in listed] == ["BBB", "CCC", "AAA"]

    def test_reorder_ignores_unknown_ids(self, client):
        a = client.post("/api/watchlist", json={"symbol": "AAA"}).json()
        resp = client.put("/api/watchlist/reorder", json={"ids": [9999, a["id"]]})
        assert resp.status_code == 200
        assert [i["symbol"] for i in resp.json()] == ["AAA"]

    def test_new_item_appears_on_top_after_reorder(self, client):
        a = client.post("/api/watchlist", json={"symbol": "AAA"}).json()
        b = client.post("/api/watchlist", json={"symbol": "BBB"}).json()
        client.put("/api/watchlist/reorder", json={"ids": [a["id"], b["id"]]})
        # A new, unpositioned item should sort to the very top.
        client.post("/api/watchlist", json={"symbol": "NEW"})
        listed = client.get("/api/watchlist").json()
        assert listed[0]["symbol"] == "NEW"

# -----------------------------------------------------------------------
# AI insights — PROMPT-ONLY (the app emits a prompt; it never calls an AI model)
# -----------------------------------------------------------------------

class TestInsightPrompts:
    def test_current_fy_label(self):
        from datetime import date
        from app.services.insights import current_fy_label

        assert current_fy_label(date(2026, 6, 4)) == "2026-27"   # mid-FY
        assert current_fy_label(date(2026, 4, 1)) == "2026-27"   # FY start
        assert current_fy_label(date(2026, 3, 31)) == "2025-26"  # FY end

    def test_watchlist_prompt_no_api_key_needed(self, client):
        client.post("/api/watchlist", json={"symbol": "INFY", "exchange": "NSE", "note": ""})

        resp = client.post("/api/insights/watchlist-suggestions/prompt", json={"count": 7})
        assert resp.status_code == 200  # NOT 503 — no AI key required
        prompt = resp.json()["prompt"]
        # The prompt tells the model to run its OWN subagents + fetch Yahoo Finance.
        assert "SUBAGENTS" in prompt.upper()
        assert "Yahoo Finance" in prompt
        # Carries the count, the schema, the buckets, and the watched symbol to avoid.
        assert "7-name" in prompt
        assert "JSON schema" in prompt and "SWAP_CANDIDATE" in prompt
        assert "INFY" in prompt

    def test_review_prompt_no_api_key_needed(self, client):
        resp = client.post(
            "/api/insights/portfolio-review/prompt", json={"target_profit_pct": 60}
        )
        assert resp.status_code == 200
        prompt = resp.json()["prompt"]
        assert "SUBAGENTS" in prompt.upper()
        assert "Yahoo Finance" in prompt
        assert "JSON schema" in prompt and "recommendations" in prompt
        # Free-cash sizing + entry/exit hints + the FY target are part of the prompt.
        assert "FREE CASH" in prompt
        assert "entry_hint" in prompt and "exit_hint" in prompt
        assert "60%" in prompt

    def test_direct_api_and_batch_routes_are_gone(self, client):
        # Prompt-only app: the AI-calling, batch, and providers routes were removed.
        assert client.post(
            "/api/insights/watchlist-suggestions", json={"count": 3}
        ).status_code == 404
        assert client.post(
            "/api/insights/recommendation", json={"symbol": "INFY"}
        ).status_code == 404
        assert client.get("/api/insights/analysis/INFY").status_code == 404
        assert client.post("/api/insights/portfolio-review", json={}).status_code == 404
        assert client.post(
            "/api/insights/portfolio-review/batch", json={}
        ).status_code == 404
        assert client.get("/api/ai/providers").status_code == 404


# -----------------------------------------------------------------------
# CSV import de-duplication
# -----------------------------------------------------------------------

class TestCSVImportDedup:
    def test_duplicate_rows_skipped(self, client):
        account = client.post("/api/accounts", json={
            "label": "Dedup Test",
            "broker": "zerodha",
            "api_key": "k",
            "api_secret": "s",
        }).json()

        csv_content = (
            b"trade_date,symbol,exchange,trade_type,quantity,price\n"
            b"2023-01-01,WIPRO,NSE,buy,20,400\n"
        )
        # Import twice
        for _ in range(2):
            client.post(
                "/api/transactions/import",
                files={"file": ("trades.csv", csv_content, "text/csv")},
                data={"account_id": account["id"]},
            )

        # Only one transaction should exist
        txns = client.get(f"/api/transactions?account_id={account['id']}").json()
        assert len(txns) == 1


# -----------------------------------------------------------------------
# Record a sale (POST /accounts/{id}/sell-shares)
# -----------------------------------------------------------------------

class TestSellShares:
    """The manual-sell flow: write a sell, re-derive holdings, book realized P&L.

    ``refresh_prices`` (the only network touch) is stubbed so tests stay offline.
    Each holding is first established via the sibling /add-shares endpoint.
    """

    def _setup(self, client, monkeypatch):
        import app.routers.accounts as accounts_router
        monkeypatch.setattr(accounts_router, "refresh_prices", lambda db, aid: 0)
        return client.post("/api/accounts", json={"label": "M", "broker": "manual"}).json()["id"]

    def _buy(self, client, aid, symbol, qty, price, when="2024-01-01"):
        return client.post(f"/api/accounts/{aid}/add-shares", json={
            "symbol": symbol, "exchange": "NSE",
            "quantity": qty, "price": price, "trade_date": when,
        })

    def test_partial_sell_reduces_qty_keeps_avg(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        self._buy(client, aid, "TCS", 10, 100)

        # Sell 4 @ ₹150 → realized = 4 × (150 − 100) = 200.
        r = client.post(f"/api/accounts/{aid}/sell-shares", json={
            "symbol": "tcs", "exchange": "NSE",  # lower-case symbol is normalised
            "quantity": 4, "price": 150, "trade_date": "2024-06-01",
        })
        assert r.status_code == 200
        assert r.json()["realized_pnl"] == 200.0

        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        tcs = next(h for h in holdings if h["symbol"] == "TCS")
        assert tcs["quantity"] == 6          # 10 − 4
        assert tcs["average_price"] == 100   # a sell leaves the average unchanged

    def test_full_sell_moves_to_exited(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        self._buy(client, aid, "INFY", 5, 200)

        r = client.post(f"/api/accounts/{aid}/sell-shares", json={
            "symbol": "INFY", "exchange": "NSE",
            "quantity": 5, "price": 250, "trade_date": "2024-06-01",
        })
        assert r.status_code == 200
        assert r.json()["realized_pnl"] == 250.0  # 5 × (250 − 200)

        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        assert all(h["symbol"] != "INFY" for h in holdings)  # no longer held

        exited = client.get(f"/api/holdings/exited?account_id={aid}").json()
        infy = next(e for e in exited if e["symbol"] == "INFY")
        assert infy["realized_pnl"] == 250.0

    def test_cannot_oversell(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        self._buy(client, aid, "WIPRO", 3, 50)
        r = client.post(f"/api/accounts/{aid}/sell-shares", json={
            "symbol": "WIPRO", "exchange": "NSE",
            "quantity": 10, "price": 60, "trade_date": "2024-06-01",
        })
        assert r.status_code == 400

    def test_cannot_sell_unheld_symbol(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        r = client.post(f"/api/accounts/{aid}/sell-shares", json={
            "symbol": "NOPE", "exchange": "NSE",
            "quantity": 1, "price": 10, "trade_date": "2024-06-01",
        })
        assert r.status_code == 400

    def test_account_not_found(self, client, monkeypatch):
        self._setup(client, monkeypatch)
        r = client.post("/api/accounts/9999/sell-shares", json={
            "symbol": "TCS", "exchange": "NSE",
            "quantity": 1, "price": 10, "trade_date": "2024-06-01",
        })
        assert r.status_code == 404


# -----------------------------------------------------------------------
# View / modify a holding's unit details (transaction CRUD)
# POST/PUT/DELETE /api/transactions + symbol-group GET
# -----------------------------------------------------------------------

class TestTransactionCrud:
    """The single-trade CRUD behind a holding: add/edit/delete a buy/sell/bonus
    and the account's holdings re-derive. ``refresh_prices`` (the only network
    touch) is stubbed so tests stay offline.
    """

    def _setup(self, client, monkeypatch):
        import app.routers.transactions as tx_router
        monkeypatch.setattr(tx_router, "refresh_prices", lambda db, aid: 0)
        return client.post("/api/accounts", json={"label": "M", "broker": "manual"}).json()["id"]

    def _add(self, client, aid, symbol, ttype, qty, price, when="2024-01-01", isin=None):
        return client.post("/api/transactions", json={
            "account_id": aid, "symbol": symbol, "exchange": "NSE",
            "trade_type": ttype, "quantity": qty, "price": price,
            "trade_date": when, "isin": isin,
        })

    def test_create_derives_holding(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        r = self._add(client, aid, "tcs", "buy", 10, 100)  # lower-case normalised
        assert r.status_code == 201
        body = r.json()
        assert body["transaction"]["symbol"] == "TCS"
        assert body["transaction"]["amount"] == 1000.0  # qty × price, server-derived

        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        tcs = next(h for h in holdings if h["symbol"] == "TCS")
        assert tcs["quantity"] == 10
        assert tcs["average_price"] == 100

    def test_bonus_is_free_and_dilutes_average(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        self._add(client, aid, "INFY", "buy", 10, 100)
        # A bonus carries no cost even if a price is sent — amount is forced to 0.
        r = self._add(client, aid, "INFY", "bonus", 10, 999)
        assert r.json()["transaction"]["amount"] == 0.0

        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        infy = next(h for h in holdings if h["symbol"] == "INFY")
        assert infy["quantity"] == 20
        assert infy["average_price"] == 50  # 1000 cost / 20 shares

    def test_edit_changes_holding(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        tx_id = self._add(client, aid, "WIPRO", "buy", 10, 100).json()["transaction"]["id"]

        r = client.put(f"/api/transactions/{tx_id}", json={"quantity": 25, "price": 80})
        assert r.status_code == 200
        assert r.json()["transaction"]["amount"] == 2000.0  # recomputed 25 × 80

        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        wipro = next(h for h in holdings if h["symbol"] == "WIPRO")
        assert wipro["quantity"] == 25
        assert wipro["average_price"] == 80

    def test_delete_rederives_and_can_empty_holding(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        keep = self._add(client, aid, "SBIN", "buy", 5, 200, when="2024-01-01").json()["transaction"]["id"]
        drop = self._add(client, aid, "SBIN", "buy", 5, 400, when="2024-02-01").json()["transaction"]["id"]

        # Two lots → avg 300. Drop the pricey lot → only the 5 @ 200 remains.
        r = client.delete(f"/api/transactions/{drop}")
        assert r.status_code == 200
        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        sbin = next(h for h in holdings if h["symbol"] == "SBIN")
        assert sbin["quantity"] == 5
        assert sbin["average_price"] == 200

        # Delete the last lot → the holding disappears entirely.
        client.delete(f"/api/transactions/{keep}")
        holdings = client.get(f"/api/holdings?account_id={aid}").json()
        assert all(h["symbol"] != "SBIN" for h in holdings)

    def test_symbol_filter_returns_only_that_holdings_group(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        self._add(client, aid, "TCS", "buy", 10, 100)
        self._add(client, aid, "TCS", "sell", 3, 150, when="2024-03-01")
        self._add(client, aid, "INFY", "buy", 7, 200)

        rows = client.get(f"/api/transactions?account_id={aid}&symbol=tcs").json()
        assert {row["symbol"] for row in rows} == {"TCS"}
        assert len(rows) == 2  # the buy and the sell, not INFY

    def test_symbol_filter_follows_rename_via_isin(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        # Same instrument, renamed ticker, linked by a shared ISIN.
        self._add(client, aid, "ZOMATO", "buy", 10, 50, isin="INE758T01015")
        self._add(client, aid, "ETERNAL", "buy", 5, 60, when="2024-05-01", isin="INE758T01015")

        rows = client.get(f"/api/transactions?account_id={aid}&symbol=ETERNAL").json()
        assert {row["symbol"] for row in rows} == {"ZOMATO", "ETERNAL"}  # one group

    def test_create_rejects_bad_trade_type(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        r = self._add(client, aid, "TCS", "dividend", 1, 10)
        assert r.status_code == 400

    def test_create_rejects_nonpositive_quantity(self, client, monkeypatch):
        aid = self._setup(client, monkeypatch)
        r = self._add(client, aid, "TCS", "buy", 0, 10)
        assert r.status_code == 400

    def test_create_account_not_found(self, client, monkeypatch):
        self._setup(client, monkeypatch)
        r = self._add(client, 9999, "TCS", "buy", 1, 10)
        assert r.status_code == 404

    def test_edit_not_found(self, client, monkeypatch):
        self._setup(client, monkeypatch)
        r = client.put("/api/transactions/9999", json={"quantity": 5})
        assert r.status_code == 404

    def test_delete_not_found(self, client, monkeypatch):
        self._setup(client, monkeypatch)
        r = client.delete("/api/transactions/9999")
        assert r.status_code == 404
