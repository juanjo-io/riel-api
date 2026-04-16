from dotenv import load_dotenv
load_dotenv(override=True)
import os
import httpx
from datetime import date, timedelta
from .base import DataProvider

BASE_URL = "https://banking.sandbox.prometeoapi.com"

class PrometeoProvider(DataProvider):

    def __init__(self):
        self._api_key  = os.getenv("PROMETEO_API_KEY")
        self._provider = os.getenv("PROMETEO_PROVIDER", "test")
        self._username = os.getenv("PROMETEO_USERNAME", "12345")
        self._password = os.getenv("PROMETEO_PASSWORD", "gfdsa")

    def provider_name(self) -> str:
        return "prometeo"

    def _login(self) -> str:
        r = httpx.post(f"{BASE_URL}/login/",
            headers={"X-API-Key": self._api_key},
            json={"provider": self._provider,
                  "username": self._username,
                  "password": self._password},
            timeout=15)
        r.raise_for_status()
        return r.json()["key"]

    def get_transactions(self, link_id: str) -> list[dict]:
        key = self._login()
        date_to   = date.today()
        date_from = date_to - timedelta(days=90)
        r = httpx.get(f"{BASE_URL}/movement/",
            headers={"X-API-Key": self._api_key},
            params={"key": key, "account": link_id,
                    "currency": "UYU",
                    "date_start": date_from.strftime("%d/%m/%Y"),
                    "date_end":   date_to.strftime("%d/%m/%Y")},
            timeout=30)
        r.raise_for_status()
        return r.json().get("movements", [])

    def get_account_summary(self, link_id: str) -> dict:
        key = self._login()
        r = httpx.get(f"{BASE_URL}/account/",
            headers={"X-API-Key": self._api_key},
            params={"key": key},
            timeout=15)
        r.raise_for_status()
        accounts = r.json().get("accounts", [])
        account  = next((a for a in accounts if a["number"] == link_id), accounts[0])
        return {"number": account["number"], "name": account["name"],
                "currency": account.get("currency"), "balance": account.get("balance")}
