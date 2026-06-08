"""
Anthropic Claude provider implementation.

Uses the official ``anthropic`` Python SDK with prompt caching on the
system prompt to reduce latency and cost on repeated calls.

Model: claude-sonnet-4-6 (configurable via ANTHROPIC_MODEL in .env)
"""
import json
from typing import Any

from app.ai.base import AIProvider
from app.config import settings


class ClaudeProvider(AIProvider):
    """AI provider backed by Anthropic Claude API with prompt caching."""

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured. "
                "Obtain a key from https://console.anthropic.com/"
            )
        # Lazy import
        import anthropic  # type: ignore[import-untyped]

        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    def complete(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict | str:
        """Call Claude and return structured dict or plain string.

        The system prompt uses ``cache_control`` so repeated calls with
        the same system prompt hit Anthropic's prompt cache, reducing
        both latency and cost.
        """
        # Build system with cache_control for prompt caching
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        if json_schema is not None:
            # Instruct the model to return valid JSON matching the schema
            user_with_schema = (
                f"{user}\n\n"
                "Respond ONLY with a valid JSON object matching this schema:\n"
                f"{json.dumps(json_schema, indent=2)}"
            )
            message = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_blocks,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user_with_schema}],
            )
            content = message.content[0].text if message.content else "{}"
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first and last lines (``` markers)
                content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            return json.loads(content)
        else:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_blocks,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user}],
            )
            return message.content[0].text if message.content else ""

    def web_search(self, system: str, user: str, max_uses: int = 6) -> str | None:
        """Run a web-search-augmented completion via the native web search tool.

        The model issues up to ``max_uses`` searches, then writes a brief. We
        concatenate all text blocks of the final message (tool_use / search
        result blocks are skipped). Returns ``None`` on any failure so the
        caller degrades gracefully.
        """
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=settings.AI_RESEARCH_MAX_TOKENS,
                system=[{"type": "text", "text": system}],  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user}],
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses,
                }],
            )
            texts = [
                b.text for b in (message.content or [])
                if getattr(b, "type", None) == "text" and getattr(b, "text", None)
            ]
            joined = "\n".join(texts).strip()
            return joined or None
        except Exception:
            return None
