"""
AI provider registry.

Selects the active provider from ``settings.AI_PROVIDER`` and manages
provider instantiation with graceful degradation:

* If the active provider's API key is not configured, ``get_provider()``
  returns ``None`` and callers should respond with HTTP 503.
* Listing providers always works regardless of key configuration.
"""
from typing import Type

from app.ai.base import AIProvider
from app.config import settings

# Registry: provider_name -> provider class
# Import here to keep things lazy if not used

PROVIDER_NAMES = ["openai", "claude"]

_PROVIDER_REGISTRY: dict[str, str] = {
    "openai": "app.ai.openai_provider.OpenAIProvider",
    "claude": "app.ai.claude_provider.ClaudeProvider",
}


def _load_class(dotted_path: str) -> Type[AIProvider]:
    """Dynamically import a class from a dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_provider() -> AIProvider | None:
    """Return an instantiated AIProvider for the configured AI_PROVIDER.

    Returns ``None`` if the provider's API key is missing so callers can
    return HTTP 503 instead of crashing.
    """
    name = settings.AI_PROVIDER.lower()
    dotted = _PROVIDER_REGISTRY.get(name)
    if dotted is None:
        return None
    try:
        cls = _load_class(dotted)
        return cls()
    except RuntimeError:
        # API key not configured
        return None
    except Exception:
        return None


def list_providers() -> list[dict]:
    """Return metadata about all known providers.

    Each entry: {name: str, active: bool, configured: bool}
    """
    active = settings.AI_PROVIDER.lower()
    result = []
    for name in PROVIDER_NAMES:
        configured = _is_configured(name)
        result.append({"name": name, "active": name == active, "configured": configured})
    return result


def _is_configured(name: str) -> bool:
    """Check whether the API key for a provider is present."""
    if name == "openai":
        return bool(settings.OPENAI_API_KEY)
    if name == "claude":
        return bool(settings.ANTHROPIC_API_KEY)
    return False
