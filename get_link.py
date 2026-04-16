import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

auth = (os.getenv("BELVO_SECRET_ID"), os.getenv("BELVO_SECRET_PASSWORD"))

attempts = [
    {"institution": "ironbank_br_business", "username": "bnk_sand_erick", "password": "full",     "access_mode": "single"},
    {"institution": "ironbank_br_business", "username": "user",            "password": "password", "access_mode": "single"},
    {"institution": "ironbank_br_business", "username": "johndoe",         "password": "test",     "access_mode": "single"},
    {"institution": "ofmockbank_br_retail", "username": "bnk_sand_erick",  "password": "full",     "access_mode": "single"},
]

for i, payload in enumerate(attempts, 1):
    print(f"--- Attempt {i}: {payload['institution']} / {payload['username']} ---")
    r = requests.post("https://sandbox.belvo.com/api/links/", auth=auth, json=payload)
    print(f"Status: {r.status_code}")
    print(json.dumps(r.json(), indent=2))
    print()
    if r.status_code in (200, 201):
        print("SUCCESS — stopping.")
        break
