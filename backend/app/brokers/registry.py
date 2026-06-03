"""
Broker connector registry.

Maps a broker identifier string (as stored in ``Account.broker``) to the
corresponding ``BrokerConnector`` subclass.

Extension guide – adding a new broker account or broker type:
1. Create the connector (see ``app/brokers/base.py`` for the interface).
2. Add an entry to ``BROKER_REGISTRY`` below.
3. Create an ``Account`` row in the DB with the matching ``broker`` string.

The rest of the application (routers, services) calls ``get_connector``
without knowing which concrete class it gets back.
"""
from typing import Type

from app.brokers.base import BrokerConnector
from app.brokers.zerodha import ZerodhaConnector

# Registry: broker_name -> connector class
BROKER_REGISTRY: dict[str, Type[BrokerConnector]] = {
    "zerodha": ZerodhaConnector,
    # Future entries, e.g.:
    # "zerodha_mf": ZerodhaMFConnector,
    # "groww":      GrowwConnector,
}


def get_connector(account: object) -> BrokerConnector:
    """Factory: build the right BrokerConnector from an Account ORM row.

    Args:
        account: An ``Account`` model instance (must have .broker,
                 .api_key, .api_secret, .access_token).

    Raises:
        ValueError: If the broker name is not in the registry.
    """
    broker_name: str = account.broker  # type: ignore[attr-defined]
    connector_cls = BROKER_REGISTRY.get(broker_name)
    if connector_cls is None:
        raise ValueError(
            f"Unknown broker '{broker_name}'. "
            f"Available brokers: {list(BROKER_REGISTRY.keys())}"
        )
    return connector_cls(
        api_key=account.api_key,  # type: ignore[attr-defined]
        api_secret=account.api_secret,  # type: ignore[attr-defined]
        access_token=account.access_token,  # type: ignore[attr-defined]
    )
