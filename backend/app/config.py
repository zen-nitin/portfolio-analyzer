"""
Application configuration loaded from environment variables / .env file.

All Kite/broker credentials are stored per-account in the database rather
than globally here, so only shared settings live in this module.
"""
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "sqlite:///./portfolio.db"

    # CORS – comma-separated origins or a list
    CORS_ORIGINS: str = "http://localhost:5173"

    # AI provider selection: "openai" | "claude"
    AI_PROVIDER: str = "openai"

    # AI web search — lets the portfolio-review agent pull LIVE sentiment and
    # forward-looking outlook (recent news, results, analyst views) rather than
    # reasoning purely from past price data. Uses the provider's native web
    # search (OpenAI Responses API / Anthropic web search tool). Degrades
    # gracefully: if unavailable, the review still runs without web context.
    AI_WEB_SEARCH: bool = True
    # Deep research: how many web searches the agent may run per research call
    # (it researches recent news + the annual report / latest results for each
    # name it could recommend), and the token budget for the research brief.
    AI_WEB_SEARCH_MAX_USES: int = 12
    AI_RESEARCH_MAX_TOKENS: int = 6000

    # AI batch mode — routes the two NON-interactive AI features (the daily
    # portfolio review and watchlist suggestions) through the provider's Batch
    # API, which is ~50% cheaper in exchange for asynchronous turnaround
    # (minutes up to the completion window). Interactive features (per-stock
    # recommendation/analysis, review chat follow-ups) always stay synchronous.
    # Degrades gracefully: when this is off, or the active provider does not
    # support batch, those features fall back to a synchronous call.
    AI_BATCH: bool = True
    AI_BATCH_COMPLETION_WINDOW: str = "24h"

    # Market data provider selection: "yfinance" (default, no API key needed)
    # yfinance is an unofficial Yahoo Finance wrapper – see app/market/README for caveats.
    MARKET_DATA_PROVIDER: str = "yfinance"

    # OpenAI
    # NOTE: A ChatGPT subscription (chat.openai.com) does NOT provide API
    # access.  You need a separate key from platform.openai.com/api-keys.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> str:
        # Accept list or comma-separated string; normalise to comma string
        if isinstance(v, list):
            return ",".join(v)
        return str(v)

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
