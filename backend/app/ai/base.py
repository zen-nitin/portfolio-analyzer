"""
Abstract AI provider interface.

Extension guide – adding a new AI provider:
1. Create ``app/ai/<name>_provider.py`` and subclass ``AIProvider``.
2. Implement ``complete(system, user, json_schema)``.
3. Add an entry to ``app/ai/registry.py`` PROVIDER_REGISTRY.
4. Set ``AI_PROVIDER=<name>`` in ``.env``.

Providers should:
* Return a ``dict`` when ``json_schema`` is supplied (structured output).
* Return a ``str`` for free-form completions.
* Raise ``RuntimeError`` if the API key is not configured – the registry
  wrapper converts this to an HTTP 503.
"""
from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Base class for AI completion providers."""

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict | str:
        """Send a chat completion request and return the model response.

        Args:
            system:      System / instruction prompt.
            user:        User message / query.
            json_schema: Optional JSON Schema dict.  When provided the
                         provider MUST return a parsed ``dict`` matching
                         the schema (using structured output / tool-use as
                         appropriate per provider).  When ``None``, returns
                         a plain string.

        Returns:
            Parsed ``dict`` if ``json_schema`` was supplied, else ``str``.
        """
