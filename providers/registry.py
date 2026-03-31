import os

from .base import DataProvider
from .belvo_provider import BelvoProvider
from .mock_provider import MockProvider

_EAGER_REGISTRY = {
    "belvo": BelvoProvider,
    "mock":  MockProvider,
}


def get_provider(name: str = None) -> DataProvider:
    """
    Return a DataProvider instance.
    `name` overrides the DATA_PROVIDER env var default.
    Env var is read at call time (not import time) so that load_dotenv()
    in main.py has already run before the first request arrives.
    PrometeoProvider is imported lazily to avoid its async SDK
    polluting event-loop state in FastAPI worker threads.
    Raises ValueError for unknown provider names.
    """
    key = (name or os.getenv("DATA_PROVIDER", "prometeo")).lower()
    if key in _EAGER_REGISTRY:
        return _EAGER_REGISTRY[key]()
    if key == "prometeo":
        from .prometeo_provider import PrometeoProvider
        return PrometeoProvider()
    raise ValueError(f"Unknown provider '{key}'. Valid options: {list(_EAGER_REGISTRY) + ['prometeo']}")
