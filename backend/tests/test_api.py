"""
Integration tests for the FastAPI application.

Uses an in-memory SQLite database and TestClient (no real network calls).
Broker and AI providers are mocked.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base, get_db
from app.main import app

# -----------------------------------------------------------------------
# In-memory test database fixture
# -----------------------------------------------------------------------

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session():
    """Provide a fresh in-memory DB session for each test."""
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session):
    """TestClient with dependency override for DB session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
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

    def test_insights_503_when_no_api_key(self, client):
        """AI endpoints must return 503 when API key not configured."""
        response = client.post(
            "/api/insights/watchlist-suggestions",
            json={"count": 3},
        )
        assert response.status_code == 503


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
