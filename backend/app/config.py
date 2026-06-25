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

    # The AI features are PROMPT-ONLY: the app calls no AI model and needs no AI
    # API key. It assembles a prompt for the user to run in Claude/ChatGPT, which
    # does its own research and returns JSON the user pastes back. (Hence there
    # are no AI_PROVIDER / OpenAI / Anthropic settings here.)

    # Market data provider selection: "yfinance" (default, no API key needed).
    # yfinance is an unofficial Yahoo Finance wrapper – see app/market/README for
    # caveats. Used for the app's own dashboards (prices, stats), NOT the AI
    # features (the AI fetches its own market data from Yahoo Finance).
    MARKET_DATA_PROVIDER: str = "yfinance"

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
