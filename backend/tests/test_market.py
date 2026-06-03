"""
Tests for the market data abstraction layer and related functionality.

All tests mock yfinance / the MarketDataProvider – no real network calls.

Coverage:
  - YFinanceProvider (unit tests with mocked yfinance)
  - MarketDataProvider registry
  - /api/market/* routes (HTTP 200, HTTP 503 on provider failure)
  - /api/market/providers
  - derive_holdings_from_transactions (buys/sells netting, weighted avg cost,
    zero-out on full sells)
  - refresh_prices (PnL computation, mocked provider)
  - manual-account sync: derives holdings + refreshes prices without Kite
  - POST /api/accounts/{id}/sync for manual account
  - POST /api/accounts/{id}/refresh-prices
  - Account creation with broker="manual" (no api_key required)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


# -----------------------------------------------------------------------
# DB fixtures
# -----------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_engine():
    import app.models.account      # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.holding      # noqa: F401
    import app.models.watchlist    # noqa: F401

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
    TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
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
# Helpers
# -----------------------------------------------------------------------

def _make_quote(symbol="RELIANCE", exchange="NSE", last_price=2500.0,
                previous_close=2480.0, day_change=20.0, day_change_pct=0.81,
                currency="INR"):
    return {
        "symbol": symbol,
        "exchange": exchange,
        "last_price": last_price,
        "previous_close": previous_close,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "currency": currency,
    }


def _mock_provider(quotes=None, stats=None, history=None, performance=None,
                   raises=None):
    """Build a mock MarketDataProvider."""
    provider = MagicMock()
    if raises:
        provider.get_quote.side_effect = raises
        provider.get_quotes.side_effect = raises
        provider.get_stats.side_effect = raises
        provider.get_history.side_effect = raises
        provider.get_performance.side_effect = raises
    else:
        if quotes is None:
            quotes = [_make_quote()]
        if isinstance(quotes, list):
            provider.get_quote.return_value = quotes[0] if quotes else _make_quote()
            provider.get_quotes.return_value = quotes
        else:
            provider.get_quote.return_value = quotes
            provider.get_quotes.return_value = [quotes]
        provider.get_stats.return_value = stats or {}
        provider.get_history.return_value = history or {
            "symbol": "RELIANCE", "exchange": "NSE", "period": "1y",
            "interval": "1d", "points": [],
        }
        provider.get_performance.return_value = performance or {
            "symbol": "RELIANCE", "exchange": "NSE",
            "returns": {"1m": 0.05, "6m": 0.12, "1y": 0.20, "5y": None},
        }
    return provider


# -----------------------------------------------------------------------
# YFinanceProvider unit tests (mock yfinance at the module level)
# -----------------------------------------------------------------------

class TestYFinanceProvider:
    def _make_fast_info(self, last_price=1500.0, previous_close=1480.0, currency="INR"):
        fi = MagicMock()
        fi.last_price = last_price
        fi.previous_close = previous_close
        fi.currency = currency
        return fi

    def _make_ticker(self, fast_info=None, info=None, history_df=None):
        ticker = MagicMock()
        ticker.fast_info = fast_info or self._make_fast_info()
        ticker.info = info or {}
        empty_df = MagicMock()
        empty_df.empty = True
        ticker.history.return_value = history_df if history_df is not None else empty_df
        return ticker

    @patch("app.market.yfinance_provider.yf")
    def test_get_quote_success(self, mock_yf):
        from app.market.yfinance_provider import YFinanceProvider
        ticker = self._make_ticker(fast_info=self._make_fast_info(1500.0, 1480.0))
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        result = provider.get_quote("INFY", "NSE")

        assert result["symbol"] == "INFY"
        assert result["exchange"] == "NSE"
        assert result["last_price"] == 1500.0
        assert result["previous_close"] == 1480.0
        assert result["currency"] == "INR"
        assert abs(result["day_change"] - 20.0) < 0.01
        assert result["day_change_pct"] is not None

    @patch("app.market.yfinance_provider.yf")
    def test_get_quote_no_price_raises_runtime_error(self, mock_yf):
        from app.market.yfinance_provider import YFinanceProvider
        fi = MagicMock()
        fi.last_price = None
        fi.previous_close = None
        fi.currency = "INR"
        ticker = self._make_ticker(fast_info=fi, info={})
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        with pytest.raises(RuntimeError, match="No price data"):
            provider.get_quote("FAKESYMBOL", "NSE")

    @patch("app.market.yfinance_provider.yf")
    def test_get_quotes_skips_failures(self, mock_yf):
        from app.market.yfinance_provider import YFinanceProvider
        fi_ok = self._make_fast_info(2500.0, 2450.0)
        fi_bad = MagicMock()
        fi_bad.last_price = None
        fi_bad.previous_close = None
        fi_bad.currency = "INR"

        ticker_ok = self._make_ticker(fast_info=fi_ok, info={})
        ticker_bad = self._make_ticker(fast_info=fi_bad, info={})
        mock_yf.Ticker.side_effect = [ticker_ok, ticker_bad]

        provider = YFinanceProvider()
        results = provider.get_quotes([("RELIANCE", "NSE"), ("FAKESYM", "NSE")])

        assert len(results) == 1
        assert results[0]["symbol"] == "RELIANCE"

    @patch("app.market.yfinance_provider.yf")
    def test_get_stats_returns_expected_fields(self, mock_yf):
        from app.market.yfinance_provider import YFinanceProvider
        info = {
            "longName": "Infosys Limited",
            "currentPrice": 1500.0,
            "marketCap": 6200000000000,
            "trailingPE": 22.5,
            "priceToBook": 6.8,
            "trailingEps": 66.5,
            "dividendYield": 0.025,
            "fiftyTwoWeekHigh": 1900.0,
            "fiftyTwoWeekLow": 1300.0,
            "beta": 0.85,
            "volume": 3500000,
            "averageVolume": 4200000,
            "dayHigh": 1520.0,
            "dayLow": 1490.0,
            "sector": "Technology",
            "industry": "IT Services",
        }
        ticker = self._make_ticker(info=info)
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        stats = provider.get_stats("INFY", "NSE")

        assert stats["symbol"] == "INFY"
        assert stats["name"] == "Infosys Limited"
        assert stats["pe_ratio"] == 22.5
        assert stats["week52_high"] == 1900.0
        assert stats["week52_low"] == 1300.0
        assert stats["sector"] == "Technology"

    @patch("app.market.yfinance_provider.yf")
    def test_get_history_success(self, mock_yf):
        import pandas as pd
        from app.market.yfinance_provider import YFinanceProvider

        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        df = pd.DataFrame(
            {"Close": [100.0, 102.0, 101.0], "Volume": [1000, 2000, 1500]},
            index=dates,
        )
        ticker = self._make_ticker(history_df=df)
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        result = provider.get_history("INFY", "1y", "1d", "NSE")

        assert result["symbol"] == "INFY"
        assert result["period"] == "1y"
        assert result["interval"] == "1d"
        assert len(result["points"]) == 3
        assert result["points"][0]["close"] == 100.0
        assert result["points"][0]["date"] == "2024-01-02"

    @patch("app.market.yfinance_provider.yf")
    def test_get_history_empty_raises(self, mock_yf):
        from app.market.yfinance_provider import YFinanceProvider
        empty_df = MagicMock()
        empty_df.empty = True
        ticker = self._make_ticker(history_df=empty_df)
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        with pytest.raises(RuntimeError):
            provider.get_history("INFY", "1y", "1d", "NSE")

    @patch("app.market.yfinance_provider.yf")
    def test_get_performance_computes_returns(self, mock_yf):
        import pandas as pd
        from app.market.yfinance_provider import YFinanceProvider

        base = pd.Timestamp("2023-01-01")
        dates = [base + pd.Timedelta(days=i) for i in range(400)]
        # Start at 100, end at 120 → positive return
        closes = [100.0] * 380 + [112.0] * 10 + [120.0] * 10
        df = pd.DataFrame({"Close": closes, "Volume": [1000] * 400}, index=dates)
        ticker = self._make_ticker(history_df=df)
        mock_yf.Ticker.return_value = ticker

        provider = YFinanceProvider()
        result = provider.get_performance("INFY", "NSE")

        assert result["symbol"] == "INFY"
        assert result["returns"] is not None
        assert result["returns"]["1y"] is not None
        assert result["returns"]["1y"] > 0

    def test_exchange_suffix_nse(self):
        from app.market.yfinance_provider import _yahoo_symbol
        assert _yahoo_symbol("INFY", "NSE") == "INFY.NS"

    def test_exchange_suffix_bse(self):
        from app.market.yfinance_provider import _yahoo_symbol
        assert _yahoo_symbol("RELIANCE", "BSE") == "RELIANCE.BO"

    def test_exchange_suffix_unknown_passthrough(self):
        from app.market.yfinance_provider import _yahoo_symbol
        assert _yahoo_symbol("TICKER", "NYSE") == "TICKER"


# -----------------------------------------------------------------------
# Market data registry
# -----------------------------------------------------------------------

class TestMarketRegistry:
    def test_get_market_provider_yfinance(self):
        from app.market.registry import get_market_provider
        from app.market.yfinance_provider import YFinanceProvider
        provider = get_market_provider()
        assert isinstance(provider, YFinanceProvider)

    def test_list_market_providers(self):
        from app.market.registry import list_market_providers
        providers = list_market_providers()
        assert isinstance(providers, list)
        names = [p["name"] for p in providers]
        assert "yfinance" in names
        yf_entry = next(p for p in providers if p["name"] == "yfinance")
        assert yf_entry["configured"] is True

    def test_unknown_provider_raises(self):
        from app.market.registry import get_market_provider
        from app.config import settings
        original = settings.MARKET_DATA_PROVIDER
        settings.MARKET_DATA_PROVIDER = "nonexistent_provider"
        try:
            with pytest.raises(RuntimeError, match="Unknown market data provider"):
                get_market_provider()
        finally:
            settings.MARKET_DATA_PROVIDER = original


# -----------------------------------------------------------------------
# /api/market/* routes
# Note: patch target is the name in the router module (where it was imported).
# -----------------------------------------------------------------------

class TestMarketRoutes:
    def test_providers_endpoint(self, client):
        response = client.get("/api/market/providers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [p["name"] for p in data]
        assert "yfinance" in names

    @patch("app.routers.market.get_market_provider")
    def test_quote_success(self, mock_get_provider, client):
        mock_get_provider.return_value = _mock_provider(quotes=[_make_quote()])
        response = client.get("/api/market/quote?symbols=RELIANCE&exchange=NSE")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["symbol"] == "RELIANCE"

    @patch("app.routers.market.get_market_provider")
    def test_quote_multiple_symbols(self, mock_get_provider, client):
        quotes = [
            _make_quote("RELIANCE", "NSE", 2500.0),
            _make_quote("INFY", "NSE", 1500.0),
        ]
        mock_get_provider.return_value = _mock_provider(quotes=quotes)
        response = client.get("/api/market/quote?symbols=RELIANCE,INFY&exchange=NSE")
        assert response.status_code == 200

    @patch("app.routers.market.get_market_provider")
    def test_quote_503_on_provider_failure(self, mock_get_provider, client):
        mock_get_provider.side_effect = RuntimeError("Yahoo Finance unavailable")
        response = client.get("/api/market/quote?symbols=RELIANCE&exchange=NSE")
        assert response.status_code == 503

    def test_quote_400_no_symbols(self, client):
        response = client.get("/api/market/quote?symbols=&exchange=NSE")
        assert response.status_code == 400

    @patch("app.routers.market.get_market_provider")
    def test_stats_success(self, mock_get_provider, client):
        stats = {
            "symbol": "INFY", "exchange": "NSE", "name": "Infosys Limited",
            "last_price": 1500.0, "market_cap": 6e12, "pe_ratio": 22.5,
            "pb_ratio": 6.8, "eps": 66.5, "dividend_yield": 0.025,
            "week52_high": 1900.0, "week52_low": 1300.0, "beta": 0.85,
            "volume": 3500000, "avg_volume": 4200000, "day_high": 1520.0,
            "day_low": 1490.0, "sector": "Technology", "industry": "IT Services",
        }
        mock_get_provider.return_value = _mock_provider(stats=stats)
        response = client.get("/api/market/stats/INFY?exchange=NSE")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "INFY"
        assert data["pe_ratio"] == 22.5

    @patch("app.routers.market.get_market_provider")
    def test_stats_503_on_provider_failure(self, mock_get_provider, client):
        mock_get_provider.side_effect = RuntimeError("Provider down")
        response = client.get("/api/market/stats/INFY?exchange=NSE")
        assert response.status_code == 503

    @patch("app.routers.market.get_market_provider")
    def test_history_success(self, mock_get_provider, client):
        history = {
            "symbol": "INFY", "exchange": "NSE", "period": "1y", "interval": "1d",
            "points": [
                {"date": "2024-01-02", "close": 1450.0, "volume": 2000000},
                {"date": "2024-01-03", "close": 1460.0, "volume": 1800000},
            ],
        }
        mock_get_provider.return_value = _mock_provider(history=history)
        response = client.get("/api/market/history/INFY?period=1y&interval=1d&exchange=NSE")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "INFY"
        assert len(data["points"]) == 2

    @patch("app.routers.market.get_market_provider")
    def test_history_503_on_provider_failure(self, mock_get_provider, client):
        mock_get_provider.side_effect = RuntimeError("Provider down")
        response = client.get("/api/market/history/INFY?exchange=NSE")
        assert response.status_code == 503

    @patch("app.routers.market.get_market_provider")
    def test_performance_success(self, mock_get_provider, client):
        perf = {
            "symbol": "INFY", "exchange": "NSE",
            "returns": {"1m": 0.03, "6m": 0.12, "1y": 0.22, "5y": None},
        }
        mock_get_provider.return_value = _mock_provider(performance=perf)
        response = client.get("/api/market/performance/INFY?exchange=NSE")
        assert response.status_code == 200
        data = response.json()
        assert data["returns"]["1y"] == 0.22
        assert data["returns"]["5y"] is None

    @patch("app.routers.market.get_market_provider")
    def test_performance_503_on_provider_failure(self, mock_get_provider, client):
        mock_get_provider.side_effect = RuntimeError("Provider down")
        response = client.get("/api/market/performance/INFY?exchange=NSE")
        assert response.status_code == 503


# -----------------------------------------------------------------------
# derive_holdings_from_transactions
# -----------------------------------------------------------------------

class TestDeriveHoldings:
    def _create_manual_account(self, db_session):
        from app.models.account import Account
        acc = Account(label="Manual Test", broker="manual")
        db_session.add(acc)
        db_session.commit()
        db_session.refresh(acc)
        return acc

    def _add_tx(self, db_session, account_id, symbol, exchange, trade_type, qty, price):
        from app.models.transaction import Transaction
        tx = Transaction(
            account_id=account_id,
            symbol=symbol.upper(),
            exchange=exchange.upper(),
            trade_type=trade_type,
            quantity=qty,
            price=price,
            amount=qty * price,
            fees=0.0,
            trade_date=date(2023, 1, 1),
        )
        db_session.add(tx)
        db_session.commit()
        return tx

    def test_simple_buy_creates_holding(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        acc = self._create_manual_account(db_session)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "buy", 10, 1500.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        assert len(holdings) == 1
        h = holdings[0]
        assert h.symbol == "INFY"
        assert h.exchange == "NSE"
        assert h.quantity == 10.0
        assert abs(h.average_price - 1500.0) < 0.01
        assert h.last_price == 0.0  # not refreshed yet

    def test_buy_then_partial_sell(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        acc = self._create_manual_account(db_session)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "buy", 10, 1500.0)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "sell", 4, 1700.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        assert len(holdings) == 1
        assert holdings[0].quantity == 6.0

    def test_full_sell_zeroes_out(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        acc = self._create_manual_account(db_session)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "buy", 10, 1500.0)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "sell", 10, 1700.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        assert len(holdings) == 0

    def test_weighted_average_cost(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        acc = self._create_manual_account(db_session)
        # Buy 10 @ 1000 = 10000, buy 10 @ 1200 = 12000 → total 20 @ avg 1100
        self._add_tx(db_session, acc.id, "TCS", "NSE", "buy", 10, 1000.0)
        self._add_tx(db_session, acc.id, "TCS", "NSE", "buy", 10, 1200.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        assert len(holdings) == 1
        assert holdings[0].quantity == 20.0
        assert abs(holdings[0].average_price - 1100.0) < 0.01

    def test_multiple_symbols(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        acc = self._create_manual_account(db_session)
        self._add_tx(db_session, acc.id, "INFY", "NSE", "buy", 5, 1500.0)
        self._add_tx(db_session, acc.id, "TCS", "NSE", "buy", 3, 3000.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        assert len(holdings) == 2
        symbols = {h.symbol for h in holdings}
        assert symbols == {"INFY", "TCS"}

    def test_replaces_existing_holdings(self, db_session):
        from app.services.holdings_derivation import derive_holdings_from_transactions
        from app.models.holding import Holding
        from datetime import datetime
        acc = self._create_manual_account(db_session)

        # Pre-existing holding
        old = Holding(
            account_id=acc.id, symbol="OLD", exchange="NSE",
            quantity=100, average_price=50, last_price=55, pnl=500,
            day_change=0, updated_at=datetime.utcnow(),
        )
        db_session.add(old)
        db_session.commit()

        # Add a new transaction for a different symbol
        self._add_tx(db_session, acc.id, "INFY", "NSE", "buy", 10, 1500.0)

        holdings = derive_holdings_from_transactions(db_session, acc.id)

        # OLD should be gone, only INFY should remain
        assert len(holdings) == 1
        assert holdings[0].symbol == "INFY"


# -----------------------------------------------------------------------
# refresh_prices
# -----------------------------------------------------------------------

class TestRefreshPrices:
    def _create_account_and_holding(self, db_session):
        from app.models.account import Account
        from app.models.holding import Holding
        from datetime import datetime

        acc = Account(label="Price Test", broker="manual")
        db_session.add(acc)
        db_session.commit()
        db_session.refresh(acc)

        holding = Holding(
            account_id=acc.id,
            symbol="INFY",
            exchange="NSE",
            quantity=10.0,
            average_price=1500.0,
            last_price=0.0,
            pnl=0.0,
            day_change=0.0,
            updated_at=datetime.utcnow(),
        )
        db_session.add(holding)
        db_session.commit()
        db_session.refresh(holding)

        return acc, holding

    @patch("app.services.price_refresh.get_market_provider")
    def test_refresh_updates_last_price_and_pnl(self, mock_get_provider, db_session):
        from app.services.price_refresh import refresh_prices

        acc, holding = self._create_account_and_holding(db_session)

        quote = _make_quote("INFY", "NSE", last_price=1600.0, previous_close=1590.0,
                             day_change=10.0)
        mock_get_provider.return_value = _mock_provider(quotes=[quote])

        count = refresh_prices(db_session, acc.id)

        assert count == 1
        db_session.refresh(holding)
        assert holding.last_price == 1600.0
        assert holding.day_change == 10.0
        # pnl = (1600 - 1500) * 10 = 1000
        assert abs(holding.pnl - 1000.0) < 0.01

    @patch("app.services.price_refresh.get_market_provider")
    def test_refresh_raises_runtime_error_when_provider_down(
        self, mock_get_provider, db_session
    ):
        from app.services.price_refresh import refresh_prices

        acc, _ = self._create_account_and_holding(db_session)
        mock_get_provider.side_effect = RuntimeError("Provider not available")

        with pytest.raises(RuntimeError):
            refresh_prices(db_session, acc.id)

    @patch("app.services.price_refresh.get_market_provider")
    def test_refresh_returns_zero_for_no_holdings(self, mock_get_provider, db_session):
        from app.services.price_refresh import refresh_prices
        from app.models.account import Account

        acc = Account(label="Empty", broker="manual")
        db_session.add(acc)
        db_session.commit()
        db_session.refresh(acc)

        mock_get_provider.return_value = _mock_provider(quotes=[])

        count = refresh_prices(db_session, acc.id)
        assert count == 0


# -----------------------------------------------------------------------
# Manual account end-to-end via HTTP
# -----------------------------------------------------------------------

class TestManualAccountSync:
    def _create_manual_account(self, client):
        resp = client.post("/api/accounts", json={
            "label": "My CSV Portfolio",
            "broker": "manual",
        })
        assert resp.status_code == 201
        return resp.json()

    def test_create_manual_account_no_creds_required(self, client):
        resp = client.post("/api/accounts", json={
            "label": "Manual Account",
            "broker": "manual",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["broker"] == "manual"
        assert data.get("api_key") is None

    def test_create_zerodha_account_requires_creds(self, client):
        resp = client.post("/api/accounts", json={
            "label": "Zerodha Account",
            "broker": "zerodha",
        })
        assert resp.status_code == 400

    def test_zerodha_account_with_creds_succeeds(self, client):
        resp = client.post("/api/accounts", json={
            "label": "Zerodha Account",
            "broker": "zerodha",
            "api_key": "k",
            "api_secret": "s",
        })
        assert resp.status_code == 201

    def test_manual_account_sync_without_access_token_works(self, client):
        """Manual accounts don't require a Kite access token."""
        account = self._create_manual_account(client)
        acc_id = account["id"]

        with patch("app.services.price_refresh.get_market_provider") as mock_market:
            mock_market.return_value = _mock_provider(quotes=[])
            resp = client.post(f"/api/accounts/{acc_id}/sync")
            assert resp.status_code == 200

    def test_zerodha_sync_requires_access_token(self, client):
        """Zerodha accounts still require a Kite access token."""
        resp = client.post("/api/accounts", json={
            "label": "Zerodha",
            "broker": "zerodha",
            "api_key": "k",
            "api_secret": "s",
        })
        acc_id = resp.json()["id"]

        resp = client.post(f"/api/accounts/{acc_id}/sync")
        assert resp.status_code == 400
        assert "access token" in resp.json()["detail"].lower()

    @patch("app.services.price_refresh.get_market_provider")
    def test_manual_sync_market_provider_down_returns_partial(
        self, mock_market, client
    ):
        account = self._create_manual_account(client)
        acc_id = account["id"]

        # Market provider is down
        mock_market.side_effect = RuntimeError("Yahoo Finance down")

        resp = client.post(f"/api/accounts/{acc_id}/sync")
        # Should still return 200 with a partial result (not 503)
        assert resp.status_code == 200
        data = resp.json()
        assert data["prices_refreshed"] == 0

    @patch("app.services.price_refresh.get_market_provider")
    def test_refresh_prices_endpoint_success(self, mock_market, client, db_session):
        from app.models.holding import Holding
        from datetime import datetime

        account = self._create_manual_account(client)
        acc_id = account["id"]

        h = Holding(
            account_id=acc_id, symbol="TCS", exchange="NSE",
            quantity=5, average_price=3000, last_price=0, pnl=0,
            day_change=0, updated_at=datetime.utcnow(),
        )
        db_session.add(h)
        db_session.commit()

        mock_market.return_value = _mock_provider(
            quotes=[_make_quote("TCS", "NSE", 3200.0)]
        )

        resp = client.post(f"/api/accounts/{acc_id}/refresh-prices")
        assert resp.status_code == 200
        data = resp.json()
        assert "prices_refreshed" in data

    @patch("app.services.price_refresh.get_market_provider")
    def test_refresh_prices_endpoint_503_on_provider_failure(
        self, mock_market, client, db_session
    ):
        from app.models.holding import Holding
        from datetime import datetime

        account = self._create_manual_account(client)
        acc_id = account["id"]

        # Need at least one holding so get_market_provider is actually called
        h = Holding(
            account_id=acc_id, symbol="INFY", exchange="NSE",
            quantity=10, average_price=1500, last_price=0, pnl=0,
            day_change=0, updated_at=datetime.utcnow(),
        )
        db_session.add(h)
        db_session.commit()

        mock_market.side_effect = RuntimeError("Provider down")

        resp = client.post(f"/api/accounts/{acc_id}/refresh-prices")
        assert resp.status_code == 503

    def test_refresh_prices_endpoint_404_for_missing_account(self, client):
        resp = client.post("/api/accounts/9999/refresh-prices")
        assert resp.status_code == 404


# -----------------------------------------------------------------------
# CSV import end-to-end with manual account
# -----------------------------------------------------------------------

class TestManualAccountCSVFlow:
    def test_csv_import_then_derive_then_refresh(self, client, db_session):
        """Full end-to-end: create manual account → import CSV → sync."""
        resp = client.post("/api/accounts", json={
            "label": "Full Test",
            "broker": "manual",
        })
        assert resp.status_code == 201
        acc_id = resp.json()["id"]

        # Import CSV
        csv_content = (
            b"trade_date,symbol,exchange,trade_type,quantity,price\n"
            b"2023-01-01,WIPRO,NSE,buy,20,400\n"
            b"2023-06-01,WIPRO,NSE,sell,5,500\n"
            b"2023-02-01,TCS,NSE,buy,3,3200\n"
        )
        resp = client.post(
            "/api/transactions/import",
            files={"file": ("trades.csv", csv_content, "text/csv")},
            data={"account_id": acc_id},
        )
        assert resp.status_code == 200
        assert resp.json()["imported"] == 3

        # Sync: derive holdings from transactions + refresh prices (mocked)
        with patch("app.services.price_refresh.get_market_provider") as mock_market:
            mock_market.return_value = _mock_provider(quotes=[
                _make_quote("WIPRO", "NSE", 450.0),
                _make_quote("TCS", "NSE", 3500.0),
            ])

            resp = client.post(f"/api/accounts/{acc_id}/sync")
            assert resp.status_code == 200
            data = resp.json()
            # 15 net WIPRO + 3 TCS = 2 holdings
            assert data["holdings_synced"] == 2
            assert data["positions_synced"] == 0

        # Verify holdings are visible
        resp = client.get(f"/api/holdings?account_id={acc_id}")
        assert resp.status_code == 200
        holdings = resp.json()
        assert len(holdings) == 2
        symbols = {h["symbol"] for h in holdings}
        assert symbols == {"WIPRO", "TCS"}
