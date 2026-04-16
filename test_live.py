import json
import requests
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = "https://web-production-f3a75.up.railway.app"

def hit(method, path, **kwargs):
    url = BASE_URL + path
    response = requests.request(method, url, **kwargs)
    print(f"{method} {path}")
    print(f"  Status : {response.status_code}")
    try:
        print(f"  Body   : {json.dumps(response.json(), indent=4)}")
    except Exception:
        print(f"  Body   : {response.text}")
    print()

hit("GET", "/")
hit("GET", "/health")
hit("POST", "/score", json={"link_id": "test-link-abc123"})
hit("POST", "/belvo-token")
