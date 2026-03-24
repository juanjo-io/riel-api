import os
from datetime import date, timedelta

import requests

from .base import DataProvider


class BelvoProvider(DataProvider):

    def __init__(self):
        self._auth = (
            os.getenv("BELVO_SECRET_ID"),
            os.getenv("BELVO_SECRET_PASSWORD"),
        )
        self._base_url = "https://sandbox.belvo.com"

    def provider_name(self) -> str:
        return "belvo"

    def get_transactions(self, link_id: str) -> list[dict]:
        date_to = date.today()
        date_from = date_to - timedelta(days=90)
        response = requests.get(
            f"{self._base_url}/api/transactions/",
            auth=self._auth,
            params={
                "link": link_id,
                "date_from": str(date_from),
                "date_to": str(date_to),
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", data if isinstance(data, list) else [])

    def get_account_summary(self, link_id: str) -> dict:
        response = requests.get(
            f"{self._base_url}/api/accounts/",
            auth=self._auth,
            params={"link": link_id},
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", data if isinstance(data, list) else [])
        return results[0] if results else {}
