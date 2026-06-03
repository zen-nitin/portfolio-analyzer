"""
OpenAI GPT provider implementation.

Uses the official ``openai`` Python SDK with JSON / structured output.

IMPORTANT NOTE ON API ACCESS:
    A ChatGPT subscription (chat.openai.com) does NOT provide programmatic
    API access.  You need a separate API key from:
        https://platform.openai.com/api-keys
    These are billed separately by token usage.
"""
import json
from typing import Any

from app.ai.base import AIProvider
from app.config import settings


class OpenAIProvider(AIProvider):
    """AI provider backed by OpenAI Chat Completions API."""

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. "
                "NOTE: A ChatGPT subscription does NOT include API access. "
                "Obtain a key from https://platform.openai.com/api-keys"
            )
        # Lazy import so the module loads even when openai is not needed
        from openai import OpenAI  # type: ignore[import-untyped]

        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL

    def complete(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict | str:
        """Call OpenAI and return structured dict or plain string."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if json_schema is not None:
            # Use structured outputs (response_format with json_schema)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        "schema": json_schema,
                    },
                },
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
            return response.choices[0].message.content or ""
