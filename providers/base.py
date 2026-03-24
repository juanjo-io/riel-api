from abc import ABC, abstractmethod


class DataProvider(ABC):

    @abstractmethod
    def get_transactions(self, link_id: str) -> list[dict]:
        """Return a list of Belvo-format transaction objects for the given link."""

    @abstractmethod
    def get_account_summary(self, link_id: str) -> dict:
        """Return a summary dict for the account associated with the given link."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return a short identifier for this provider (e.g. 'belvo', 'mock')."""
