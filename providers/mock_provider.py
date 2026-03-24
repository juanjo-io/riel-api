import json
import os

from .base import DataProvider

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class MockProvider(DataProvider):

    def provider_name(self) -> str:
        return "mock"

    def get_transactions(self, link_id: str) -> list[dict]:
        path = os.path.join(_BASE_DIR, "sample_transactions.json")
        with open(path) as f:
            return json.load(f)

    def get_account_summary(self, link_id: str) -> dict:
        return {
            "id": "acc-mock-001",
            "link": link_id,
            "institution": {"name": "Mock Bank Colombia"},
            "category": "CHECKING_ACCOUNT",
            "currency": "COP",
            "balance": {"current": 1_250_000, "available": 1_100_000},
        }
