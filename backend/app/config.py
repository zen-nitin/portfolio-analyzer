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
