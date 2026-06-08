"""
OpenAI GPT provider implementation.

Uses the official ``openai`` Python SDK with JSON / structured output.

IMPORTANT NOTE ON API ACCESS:
    A ChatGPT subscription (chat.openai.com) does NOT provide programmatic
    API access.  You need a separate API key from:
        https://platform.openai.com/api-keys
    These are billed separately by token usage.
"""
import io
import json
from typing import Any

from app.ai.base import AIProvider
from app.config import settings


def _structured_response_format(json_schema: dict[str, Any]) -> dict[str, Any]:
    """The Chat Completions ``response_format`` for strict structured output.

    Shared by the synchronous ``complete`` path and the batched request bodies
    so both ask the model for output in exactly the same shape.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "response",
            "strict": True,
            "schema": json_schema,
        },
    }


class OpenAIProvider(AIProvider):
    """AI provider backed by OpenAI Chat Completions API."""

    #: OpenAI exposes a Batch API (~50% cheaper, async) — see submit/poll below.
    supports_batch = True

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
                response_format=_structured_response_format(json_schema),
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
            return response.choices[0].message.content or ""

    def web_search(self, system: str, user: str, max_uses: int = 6) -> str | None:
        """Run a web-search-augmented completion via the Responses API.

        Uses the built-in ``web_search`` tool so the model can browse for
        current information. Returns the aggregated text, or ``None`` on any
        failure (older SDK/model without web search, network error, etc.) so
        the caller degrades gracefully.
        """
        try:
            response = self._client.responses.create(
                model=self._model,
                tools=[{"type": "web_search"}],
                instructions=system,
                input=user,
            )
            text = (getattr(response, "output_text", None) or "").strip()
            return text or None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Batch API (~50% cheaper, asynchronous)
    # ------------------------------------------------------------------

    # OpenAI batch statuses → our normalized set.
    _STATUS_MAP = {
        "validating": "pending",
        "in_progress": "pending",
        "finalizing": "pending",
        "completed": "completed",
        "failed": "failed",
        "expired": "expired",
        "cancelling": "cancelled",
        "cancelled": "cancelled",
    }

    def submit_batch(self, items: list[dict[str, Any]]) -> str:
        """Upload a JSONL of chat-completion requests and create a batch job."""
        lines = []
        for item in items:
            body: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": item["system"]},
                    {"role": "user", "content": item["user"]},
                ],
            }
            schema = item.get("json_schema")
            if schema is not None:
                body["response_format"] = _structured_response_format(schema)
            lines.append(
                {
                    "custom_id": item["custom_id"],
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": body,
                }
            )

        payload = "\n".join(json.dumps(line) for line in lines).encode("utf-8")
        upload = self._client.files.create(
            file=io.BytesIO(payload),
            purpose="batch",
        )
        batch = self._client.batches.create(
            input_file_id=upload.id,
            endpoint="/v1/chat/completions",
            completion_window=settings.AI_BATCH_COMPLETION_WINDOW,
        )
        return batch.id

    def poll_batch(self, batch_id: str) -> dict[str, Any]:
        """Retrieve batch status and, when done, parse its output JSONL."""
        batch = self._client.batches.retrieve(batch_id)
        status = self._STATUS_MAP.get(batch.status, "pending")

        if status != "completed":
            error = None
            if status in ("failed", "expired", "cancelled"):
                error = f"Batch {batch.status}."
            return {"status": status, "results": {}, "error": error}

        # Completed — download and parse the output file (JSONL, one line/request).
        output_file_id = getattr(batch, "output_file_id", None)
        if not output_file_id:
            return {"status": "failed", "results": {}, "error": "No output file."}

        content = self._client.files.content(output_file_id)
        text = content.text if hasattr(content, "text") else content.read().decode("utf-8")

        results: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            custom_id = row.get("custom_id")
            try:
                msg = row["response"]["body"]["choices"][0]["message"]["content"]
                results[custom_id] = json.loads(msg)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                # Surface raw content if structured parsing fails.
                results[custom_id] = row.get("response", {})

        return {"status": "completed", "results": results, "error": None}
