import os

from .base import DataProvider
from .belvo_provider import BelvoProvider
from .mock_provider import MockProvider

_DEFAULT = os.getenv("DATA_PROVIDER", "belvo")

_REGISTRY = {
    "belvo": BelvoProvider,
    "mock":  MockProvider,
}


def get_provider(name: str = None) -> DataProvider:
    """
    Return a DataProvider instance.
    `name` overrides the DATA_PROVIDER env var default.
    Raises ValueError for unknown provider names.
    """
    key = (name or _DEFAULT).lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(f"Unknown provider '{key}'. Valid options: {list(_REGISTRY)}")
    return cls()
