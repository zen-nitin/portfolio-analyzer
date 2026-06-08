"""
Tests for AI batch mode (the daily portfolio review + watchlist suggestions
routed through the provider Batch API).

Hermetic: no network. A fake provider implements the batch interface, and the
OpenAI provider's batch methods are exercised against a fake OpenAI client.
"""
import json
import os
import tempfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


# -----------------------------------------------------------------------
# Fixtures (mirrors test_api.py — there is no shared conftest)
# -----------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_engine():
    import app.models.account      # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.ledger       # noqa: F401
    import app.models.holding      # noqa: F401
    import app.models.watchlist    # noqa: F401
    import app.models.cash         # noqa: F401

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
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
# Fake provider implementing the batch interface
# -----------------------------------------------------------------------

REVIEW_PAYLOAD = {
    "answer": "Trim the laggards, add to quality.",
    "portfolio_commentary": "On track but concentrated.",
    "recommendations": [
        {
            "symbol": "INFY", "exchange": "NSE", "position": "WATCHLIST",
            "action": "BUY", "conviction": 0.7, "rationale": "Quality compounder.",
        },
    ],
}

WATCHLIST_PAYLOAD = {
    "suggestions": [
        {"symbol": "TCS", "exchange": "NSE", "rationale": "Defensive cash machine."},
    ],
}


class _FakeBatchProvider:
    """Stand-in AIProvider implementing the optional batch interface."""

    supports_batch = True

    def __init__(self, results=None, status="completed", error=None):
        self._results = results or {}
        self._status = status
        self._error = error
        self.submit_calls = 0
        self.submitted_items = None

    def complete(self, system, user, json_schema=None):
        # Used by the synchronous fallback path.
        return next(iter(self._results.values()), {})

    def web_search(self, system, user, max_uses=6):
        return None

    def submit_batch(self, items):
        self.submit_calls += 1
        self.submitted_items = items
        return "batch_test_123"

    def poll_batch(self, batch_id):
        if self._status != "completed":
            return {"status": self._status, "results": {}, "error": self._error}
        return {"status": "completed", "results": dict(self._results), "error": None}


def _wire(monkeypatch, provider):
    """Point the insights service at a fake provider with no network access."""
    import app.services.insights as insights_service

    monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: provider)
    monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})
    # Structured idea pools / per-holding stats would otherwise hit the network.
    monkeypatch.setattr(insights_service, "_fetch_movers", lambda count=10: {"gainers": [], "losers": []})
    monkeypatch.setattr(insights_service, "_fetch_market_stats", lambda symbol, exchange: None)
    monkeypatch.setattr(insights_service, "_fetch_sector_leaders", lambda: [])
    monkeypatch.setattr(insights_service, "_fetch_growth_leaders", lambda: [])
    monkeypatch.setattr(insights_service, "_fetch_industry_peers", lambda industries, exclude: {})
    # Keep web search out of the test (otherwise it would call provider.web_search).
    monkeypatch.setattr(insights_service.ai_registry.settings, "AI_WEB_SEARCH", False)


# -----------------------------------------------------------------------
# Route tests: submit -> poll
# -----------------------------------------------------------------------

class TestBatchRoutes:
    def test_submit_review_returns_pending_batch_id(self, client, monkeypatch):
        provider = _FakeBatchProvider(results={"portfolio_review": REVIEW_PAYLOAD})
        _wire(monkeypatch, provider)

        resp = client.post("/api/insights/portfolio-review/batch", json={"target_profit_pct": 75})
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] == "batch_test_123"
        assert data["status"] == "pending"
        assert provider.submit_calls == 1
        # The single batched item carries the review prompt + schema.
        assert provider.submitted_items[0]["custom_id"] == "portfolio_review"
        assert provider.submitted_items[0]["json_schema"] is not None

    def test_poll_review_completed_shapes_result(self, client, monkeypatch):
        provider = _FakeBatchProvider(results={"portfolio_review": REVIEW_PAYLOAD})
        _wire(monkeypatch, provider)

        resp = client.get(
            "/api/insights/batch/batch_test_123",
            params={"feature": "portfolio_review", "target_profit_pct": 75},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        result = data["result"]
        # Shaped identically to the synchronous endpoint.
        assert result["target_profit_pct"] == 75
        assert "fy" in result
        assert result["recommendations"][0]["symbol"] == "INFY"

    def test_poll_pending_returns_pending(self, client, monkeypatch):
        provider = _FakeBatchProvider(status="in_progress_unused", results={})
        provider._status = "pending"
        _wire(monkeypatch, provider)

        resp = client.get(
            "/api/insights/batch/batch_test_123",
            params={"feature": "portfolio_review"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_poll_failed_surfaces_error(self, client, monkeypatch):
        provider = _FakeBatchProvider(status="failed", error="Batch failed.")
        _wire(monkeypatch, provider)

        resp = client.get(
            "/api/insights/batch/batch_test_123",
            params={"feature": "portfolio_review"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"] == "Batch failed."

    def test_submit_watchlist_then_poll(self, client, monkeypatch):
        provider = _FakeBatchProvider(results={"watchlist_suggestions": WATCHLIST_PAYLOAD})
        _wire(monkeypatch, provider)

        submit = client.post("/api/insights/watchlist-suggestions/batch", json={"count": 3})
        assert submit.status_code == 200
        assert submit.json()["status"] == "pending"

        poll = client.get(
            "/api/insights/batch/batch_test_123",
            params={"feature": "watchlist_suggestions"},
        )
        assert poll.status_code == 200
        result = poll.json()["result"]
        assert result["suggestions"][0]["symbol"] == "TCS"

    def test_submit_falls_back_to_sync_when_batch_disabled(self, client, monkeypatch):
        provider = _FakeBatchProvider(results={"portfolio_review": REVIEW_PAYLOAD})
        _wire(monkeypatch, provider)
        # Turn batch mode off at the router's settings singleton.
        import app.routers.insights as insights_router
        monkeypatch.setattr(insights_router.settings, "AI_BATCH", False)

        resp = client.post("/api/insights/portfolio-review/batch", json={"target_profit_pct": 50})
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] is None
        assert data["status"] == "completed"
        assert data["result"]["target_profit_pct"] == 50
        assert provider.submit_calls == 0  # never submitted a batch

    def test_submit_falls_back_when_provider_unsupported(self, client, monkeypatch):
        provider = _FakeBatchProvider(results={"watchlist_suggestions": WATCHLIST_PAYLOAD})
        provider.supports_batch = False  # provider has no batch capability
        _wire(monkeypatch, provider)

        resp = client.post("/api/insights/watchlist-suggestions/batch", json={"count": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] is None
        assert data["status"] == "completed"
        assert data["result"]["suggestions"][0]["symbol"] == "TCS"

    def test_poll_503_when_provider_unsupported(self, client, monkeypatch):
        provider = _FakeBatchProvider()
        provider.supports_batch = False
        _wire(monkeypatch, provider)

        resp = client.get(
            "/api/insights/batch/batch_test_123",
            params={"feature": "portfolio_review"},
        )
        assert resp.status_code == 503

    def test_submit_503_when_no_provider(self, client, monkeypatch):
        import app.services.insights as insights_service
        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: None)

        resp = client.post("/api/insights/watchlist-suggestions/batch", json={"count": 3})
        assert resp.status_code == 503


class TestExternalPrompt:
    """The 'generate elsewhere' prompt endpoints need NO AI provider."""

    def _no_network(self, monkeypatch):
        import app.services.insights as insights_service
        monkeypatch.setattr(insights_service.ai_registry, "get_provider", lambda: None)
        monkeypatch.setattr(insights_service, "_fetch_quotes", lambda items: {})
        monkeypatch.setattr(insights_service, "_fetch_market_stats", lambda s, e: None)
        monkeypatch.setattr(
            insights_service, "_fetch_movers", lambda count=10: {"gainers": [], "losers": []}
        )
        monkeypatch.setattr(insights_service, "_fetch_sector_leaders", lambda: [])
        monkeypatch.setattr(insights_service, "_fetch_growth_leaders", lambda: [])
        monkeypatch.setattr(insights_service, "_fetch_industry_peers", lambda industries, exclude: {})

    def test_watchlist_prompt_no_provider_needed(self, client, monkeypatch):
        self._no_network(monkeypatch)
        resp = client.post("/api/insights/watchlist-suggestions/prompt", json={"count": 10})
        assert resp.status_code == 200  # NOT 503 — no API key required
        prompt = resp.json()["prompt"]
        assert "JSON schema" in prompt and "SWAP_CANDIDATE" in prompt

    def test_review_prompt_no_provider_needed(self, client, monkeypatch):
        self._no_network(monkeypatch)
        resp = client.post("/api/insights/portfolio-review/prompt", json={"target_profit_pct": 75})
        assert resp.status_code == 200
        prompt = resp.json()["prompt"]
        assert "JSON schema" in prompt and "recommendations" in prompt


# -----------------------------------------------------------------------
# OpenAI provider batch unit tests (fake OpenAI client — no network)
# -----------------------------------------------------------------------

class _FakeFiles:
    def __init__(self, output_text=""):
        self.uploaded = None
        self._output_text = output_text

    def create(self, file, purpose):
        self.uploaded = (file.read(), purpose)
        return SimpleNamespace(id="file_in_1")

    def content(self, file_id):
        return SimpleNamespace(text=self._output_text)


class _FakeBatches:
    def __init__(self, status="completed"):
        self.created = None
        self._status = status

    def create(self, input_file_id, endpoint, completion_window):
        self.created = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        return SimpleNamespace(id="batch_1")

    def retrieve(self, batch_id):
        return SimpleNamespace(status=self._status, output_file_id="file_out_1")


def _make_openai_provider(monkeypatch):
    import app.ai.openai_provider as op
    monkeypatch.setattr(op.settings, "OPENAI_API_KEY", "test-key")
    provider = op.OpenAIProvider()
    return provider


class TestOpenAIBatch:
    def test_submit_batch_builds_jsonl_and_uploads(self, monkeypatch):
        provider = _make_openai_provider(monkeypatch)
        files = _FakeFiles()
        batches = _FakeBatches()
        provider._client = SimpleNamespace(files=files, batches=batches)

        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        batch_id = provider.submit_batch(
            [{"custom_id": "portfolio_review", "system": "S", "user": "U", "json_schema": schema}]
        )

        assert batch_id == "batch_1"
        assert batches.created["endpoint"] == "/v1/chat/completions"
        # The uploaded JSONL line is a well-formed chat-completions request.
        payload, purpose = files.uploaded
        assert purpose == "batch"
        line = json.loads(payload.decode("utf-8").strip())
        assert line["custom_id"] == "portfolio_review"
        assert line["url"] == "/v1/chat/completions"
        body = line["body"]
        assert body["messages"][0]["role"] == "system"
        assert body["response_format"]["type"] == "json_schema"

    def test_poll_batch_parses_completed_output(self, monkeypatch):
        provider = _make_openai_provider(monkeypatch)
        output_line = json.dumps({
            "custom_id": "watchlist_suggestions",
            "response": {
                "body": {
                    "choices": [
                        {"message": {"content": json.dumps(WATCHLIST_PAYLOAD)}}
                    ]
                }
            },
        })
        provider._client = SimpleNamespace(
            files=_FakeFiles(output_text=output_line),
            batches=_FakeBatches(status="completed"),
        )

        out = provider.poll_batch("batch_1")
        assert out["status"] == "completed"
        assert out["results"]["watchlist_suggestions"]["suggestions"][0]["symbol"] == "TCS"

    def test_poll_batch_maps_in_progress_to_pending(self, monkeypatch):
        provider = _make_openai_provider(monkeypatch)
        provider._client = SimpleNamespace(
            files=_FakeFiles(),
            batches=_FakeBatches(status="in_progress"),
        )
        out = provider.poll_batch("batch_1")
        assert out["status"] == "pending"
        assert out["results"] == {}
