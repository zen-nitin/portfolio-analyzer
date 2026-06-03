"""
Market data provider registry.

Selects the active provider from ``settings.MARKET_DATA_PROVIDER`` and
manages provider instantiation with graceful degradation:

* If the active provider fails to initialise, ``get_market_provider()``
  raises ``RuntimeError`` which the router converts to HTTP 503.
* yfinance requires no API key (configured=True always).
* Listing providers always works regardless of configuration.

Extension guide – adding a new market data provider:
1. Create ``app/market/<name>_provider.py`` (subclass ``MarketDataProvider``).
2. Add an entry to ``MARKET_PROVIDER_NAMES`` and ``_PROVIDER_REGISTRY`` below.
3. Add a ``_is_configured`` branch if your provider needs an API key.
4. Set ``MARKET_DATA_PROVIDER=<name>`` in ``.env``.
"""
from typing import Type

from app.market.base import MarketDataProvider
from app.config import settings

MARKET_PROVIDER_NAMES = ["yfinance"]

_PROVIDER_REGISTRY: dict[str, str] = {
    "yfinance": "app.market.yfinance_provider.YFinanceProvider",
}


def _load_class(dotted_path: str) -> Type[MarketDataProvider]:
    """Dynamically import a class from a dotted module path."""
    import importlib
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_market_provider() -> MarketDataProvider:
    """Return an instantiated MarketDataProvider for the configured backend.

    Raises:
        RuntimeError: If the provider name is not recognised or the provider
            fails to initialise.  Callers should convert this to HTTP 503.
    """
    name = settings.MARKET_DATA_PROVIDER.lower()
    dotted = _PROVIDER_REGISTRY.get(name)
    if dotted is None:
        raise RuntimeError(
            f"Unknown market data provider '{name}'. "
            f"Available providers: {MARKET_PROVIDER_NAMES}"
        )
    cls = _load_class(dotted)
    return cls()


def list_market_providers() -> list[dict]:
    """Return metadata about all known market data providers.

    Each entry: {name: str, active: bool, configured: bool}
    """
    active = settings.MARKET_DATA_PROVIDER.lower()
    result = []
    for name in MARKET_PROVIDER_NAMES:
        configured = _is_configured(name)
        result.append({"name": name, "active": name == active, "configured": configured})
    return result


def _is_configured(name: str) -> bool:
    """Check whether the provider is usable (key present or key-free)."""
    # yfinance requires no API key – always configured
    if name == "yfinance":
        return True
    return False
