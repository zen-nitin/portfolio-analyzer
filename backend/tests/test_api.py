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
# AI Providers
# -----------------------------------------------------------------------

class TestAIProviders:
    def test_list_providers(self, client):
        response = client.get("/api/ai/providers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [p["name"] for p in data]
        assert "openai" in names
        assert "claude" in names
        for p in data:
            assert "active" in p
            assert "configured" in p

    def test_insights_503_when_no_api_key(self, client, monkeypatch):
        """AI endpoints must return 503 when the provider is unavailable.

        Force ``get_provider`` to ``None`` so this is hermetic — it must hold
        regardless of whether a real API key happens to be set in the dev env,
        and it must never make a live API/web-search call from the test suite.
        """
        import app.services.insights as insights_service

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: None)
        response = client.post(
            "/api/insights/watchlist-suggestions",
            json={"count": 3},
        )
        assert response.status_code == 503


# -----------------------------------------------------------------------
# Portfolio review (AI analysis of holdings + watchlist vs FY goal)
# -----------------------------------------------------------------------


class _FakeProvider:
    """Stand-in AIProvider that echoes a fixed structured payload."""

    def __init__(self, payload):
        self._payload = payload

    def complete(self, system, user, json_schema=None):
        return self._payload


class TestPortfolioReview:
    def test_current_fy_label(self):
        from datetime import date
        from app.services.insights import current_fy_label

        assert current_fy_label(date(2026, 6, 4)) == "2026-27"   # mid-FY
        assert current_fy_label(date(2026, 4, 1)) == "2026-27"   # FY start
        assert current_fy_label(date(2026, 3, 31)) == "2025-26"  # FY end
        assert current_fy_label(date(2026, 2, 10)) == "2025-26"  # Jan–Mar

    def test_review_success(self, client, monkeypatch):
        import app.services.insights as insights_service

        client.post("/api/watchlist", json={"symbol": "INFY", "exchange": "NSE", "note": ""})

        payload = {
            "answer": "Lean into your watchlist quality names.",
            "portfolio_commentary": "Goal is a stretch from here.",
            "recommendations": [
                {
                    "symbol": "INFY", "exchange": "NSE", "position": "WATCHLIST",
                    "action": "BUY", "conviction": 0.8, "rationale": "Quality compounder.",
                },
            ],
        }
        monkeypatch.setattr(
            insights_service.ai_registry, "get_provider", lambda: _FakeProvider(payload)
        )
        # Don't hit the network for watchlist quotes.
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})

        response = client.post(
            "/api/insights/portfolio-review", json={"target_profit_pct": 75}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["target_profit_pct"] == 75
        assert data["fy"]  # FY label injected by the service
        assert data["answer"] == "Lean into your watchlist quality names."
        assert data["portfolio_commentary"] == "Goal is a stretch from here."
        assert data["recommendations"][0]["action"] == "BUY"
        assert data["recommendations"][0]["symbol"] == "INFY"

    def test_review_follow_up_question(self, client, monkeypatch):
        """A conversation transcript is passed through; the last user turn is the question."""
        import app.services.insights as insights_service

        captured = {}

        class _CapturingProvider:
            def complete(self, system, user, json_schema=None):
                captured["user"] = user
                return {
                    "answer": "Understood — keeping LICI.",
                    "portfolio_commentary": "Revised plan.",
                    "recommendations": [],
                }

        monkeypatch.setattr(
            insights_service.ai_registry, "get_provider", lambda: _CapturingProvider()
        )
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})

        response = client.post(
            "/api/insights/portfolio-review",
            json={
                "target_profit_pct": 75,
                "messages": [{"role": "user", "content": "Do not sell LICI, what else?"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["answer"] == "Understood — keeping LICI."
        # The question must reach the prompt.
        assert "Do not sell LICI" in captured["user"]
        # New: free cash + entry/exit-hint guidance are part of the review prompt.
        assert "FREE CASH to deploy" in captured["user"]
        assert "entry_hint" in captured["user"]
        assert "exit_hint" in captured["user"]

    def test_review_503_when_no_provider(self, client, monkeypatch):
        import app.services.insights as insights_service

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: None)
        response = client.post("/api/insights/portfolio-review", json={})
        assert response.status_code == 503

    def test_web_research_injected_into_prompt(self, client, monkeypatch):
        """When the provider supports web search, its brief is fed into the review prompt."""
        import app.services.insights as insights_service

        client.post("/api/watchlist", json={"symbol": "INFY", "exchange": "NSE", "note": ""})

        captured = {}

        class _WebProvider:
            def web_search(self, system, user, max_uses=6):
                captured["search_user"] = user
                return "INFY: new large deal win, analysts turning bullish (as of May)."

            def complete(self, system, user, json_schema=None):
                captured["review_user"] = user
                return {"answer": "ok", "portfolio_commentary": "c", "recommendations": []}

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: _WebProvider())
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})
        monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", True)

        response = client.post("/api/insights/portfolio-review", json={"target_profit_pct": 50})
        assert response.status_code == 200
        # The web brief reached the structured review prompt under a DEEP RESEARCH header.
        assert "DEEP RESEARCH" in captured["review_user"]
        # The research ask now demands annual-report / results fundamentals, not just news.
        assert "ANNUAL REPORT" in captured["search_user"].upper()
        assert "FUNDAMENTALS" in captured["search_user"].upper()
        assert "analysts turning bullish" in captured["review_user"]
        # And the symbol was part of what we asked the search to research.
        assert "INFY" in captured["search_user"]

    def test_web_research_skipped_on_followup(self, client, monkeypatch):
        """Follow-up chat turns must not trigger a fresh web search."""
        import app.services.insights as insights_service

        calls = {"search": 0}

        class _WebProvider:
            def web_search(self, system, user, max_uses=6):
                calls["search"] += 1
                return "should not be called"

            def complete(self, system, user, json_schema=None):
                return {"answer": "a", "portfolio_commentary": "c", "recommendations": []}

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: _WebProvider())
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})
        monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", True)

        response = client.post(
            "/api/insights/portfolio-review",
            json={"messages": [{"role": "user", "content": "what about IT stocks?"}]},
        )
        assert response.status_code == 200
        assert calls["search"] == 0

    def test_web_research_graceful_when_search_errors(self, client, monkeypatch):
        """A failing web_search must not break the review (degrades to no web context)."""
        import app.services.insights as insights_service

        class _BoomProvider:
            def web_search(self, system, user, max_uses=6):
                raise RuntimeError("search backend down")

            def complete(self, system, user, json_schema=None):
                return {"answer": "still works", "portfolio_commentary": "c", "recommendations": []}

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: _BoomProvider())
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})
        monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", True)

        response = client.post("/api/insights/portfolio-review", json={})
        assert response.status_code == 200
        assert response.json()["answer"] == "still works"

    def test_base_provider_web_search_returns_none(self):
        from app.ai.base import AIProvider

        class _Min(AIProvider):
            def complete(self, system, user, json_schema=None):
                return "x"

        assert _Min().web_search("s", "u") is None


class TestWatchlistSuggestionsWebSearch:
    def test_movers_and_research_injected(self, client, monkeypatch):
        """Watchlist suggestions inject structured top movers + a web-research
        brief into the suggestion prompt."""
        import app.services.insights as insights_service

        captured = {}

        class _WebProvider:
            def web_search(self, system, user, max_uses=6):
                captured["search_system"] = system
                captured["search_user"] = user
                return "ABC — up 12% on a large order win; strong forward outlook."

            def complete(self, system, user, json_schema=None):
                captured["suggest_user"] = user
                return {"suggestions": [
                    {"symbol": "ABC", "exchange": "NSE", "bucket": "TACTICAL",
                     "rationale": "Order win catalyst.", "risk": "HIGH", "horizon": "1-2 quarters",
                     "catalyst": "Large order win", "exit_trigger": "After Q2 results", "replaces": None},
                ], "flagged_holdings": []}

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: _WebProvider())
        monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", True)
        # All structured idea pools come from the market provider — mock (no network).
        monkeypatch.setattr(
            insights_service, "_fetch_movers",
            lambda count=10: {"gainers": [{"symbol": "MOV", "exchange": "NSE",
                                           "change_pct": 5.0, "name": "Mover Co"}], "losers": []},
        )
        monkeypatch.setattr(
            insights_service, "_fetch_sector_leaders",
            lambda: [{"symbol": "SECLEAD", "exchange": "NSE", "sector": "Technology"}],
        )
        monkeypatch.setattr(
            insights_service, "_fetch_growth_leaders",
            lambda: [{"symbol": "GROWCO", "exchange": "NSE"}],
        )
        monkeypatch.setattr(
            insights_service, "_fetch_industry_peers",
            lambda industries, exclude: {"Information Technology Services": [{"symbol": "PEERCO"}]},
        )

        response = client.post("/api/insights/watchlist-suggestions", json={"count": 3})
        assert response.status_code == 200
        assert response.json()["suggestions"][0]["symbol"] == "ABC"
        # The research focuses on catalysts now (gainers/losers are structured).
        # Research now deep-digs catalysts AND annual-report fundamentals.
        sysu = captured["search_system"].upper()
        assert "CATALYST" in sysu and "ANNUAL REPORT" in sysu
        # All idea pools and the web brief reached the suggestion prompt.
        u = captured["suggest_user"]
        assert "TOP MOVERS" in u and "MOV" in u
        assert "SECTOR LEADERS" in u and "SECLEAD" in u
        assert "HIGH-GROWTH COMPANIES" in u and "GROWCO" in u
        assert "COMPETITIVE SET" in u and "PEERCO" in u
        assert "DEEP RESEARCH" in u

    def test_suggestions_work_without_web_search(self, client, monkeypatch):
        """When the provider has no web search, suggestions still come back."""
        import app.services.insights as insights_service

        class _PlainProvider:
            def complete(self, system, user, json_schema=None):
                return {"suggestions": [
                    {"symbol": "DEF", "exchange": "NSE", "rationale": "Quality compounder."},
                ]}

        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: _PlainProvider())
        monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", True)
        monkeypatch.setattr(
            insights_service, "_fetch_movers", lambda count=10: {"gainers": [], "losers": []}
        )
        monkeypatch.setattr(insights_service, "_fetch_sector_leaders", lambda: [])
        monkeypatch.setattr(insights_service, "_fetch_growth_leaders", lambda: [])
        monkeypatch.setattr(insights_service, "_fetch_industry_peers", lambda industries, exclude: {})

        response = client.post("/api/insights/watchlist-suggestions", json={"count": 2})
        assert response.status_code == 200
        assert response.json()["suggestions"][0]["symbol"] == "DEF"


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
