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
* Optionally override ``web_search`` to expose native web search (used to feed
  live sentiment / forward-looking research into the portfolio review). The
  default returns ``None`` (no web search), so callers must degrade gracefully.
"""
from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Base class for AI completion providers."""

    #: Whether this provider implements the asynchronous batch interface below.
    #: Providers that leave this ``False`` (the default) are treated as
    #: batch-unsupported and callers fall back to synchronous ``complete``.
    supports_batch: bool = False

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

    def web_search(self, system: str, user: str, max_uses: int = 6) -> str | None:
        """Run a web-search-augmented completion and return free-form text.

        Implementations should enable the provider's native web search tool so
        the model can look up current, time-sensitive information (news,
        results, analyst views, sentiment) and return a concise written brief
        with sources woven in.

        Returns ``None`` when web search is unavailable for this provider /
        configuration, or on any error — callers MUST treat ``None`` as "no web
        context" and continue. The default implementation performs no search.
        """
        return None

    # ------------------------------------------------------------------
    # Optional asynchronous batch interface (cost-saving, ~50% cheaper).
    #
    # Only the non-interactive AI features (daily portfolio review, watchlist
    # suggestions) use this. Providers opt in by setting ``supports_batch =
    # True`` and implementing both methods. The default implementations raise,
    # so callers MUST gate on ``supports_batch`` and fall back to ``complete``.
    # ------------------------------------------------------------------

    def submit_batch(self, items: list[dict[str, Any]]) -> str:
        """Submit a batch of structured-output completions; return a batch id.

        Each item is a dict with keys:
            ``custom_id``  – caller-chosen id used to map results back.
            ``system``     – system / instruction prompt.
            ``user``       – user message.
            ``json_schema``– JSON Schema for structured output (required here;
                             every batched feature uses structured output).

        Returns the provider's batch identifier (poll it with ``poll_batch``).
        Raises ``NotImplementedError`` when the provider has no batch support.
        """
        raise NotImplementedError("This provider does not support batch mode.")

    def poll_batch(self, batch_id: str) -> dict[str, Any]:
        """Poll a previously submitted batch.

        Returns a dict::

            {
                "status": "pending" | "completed" | "failed"
                          | "expired" | "cancelled",
                "results": {custom_id: dict | str, ...},  # only when completed
                "error": str | None,
            }

        ``results`` maps each ``custom_id`` to the parsed structured ``dict``
        (or raw ``str``). Raises ``NotImplementedError`` when unsupported.
        """
        raise NotImplementedError("This provider does not support batch mode.")
