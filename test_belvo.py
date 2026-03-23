import requests
from dotenv import load_dotenv
import os
import json

load_dotenv()

secret_id = os.getenv("BELVO_SECRET_ID")
secret_password = os.getenv("BELVO_SECRET_PASSWORD")
base_url = "https://sandbox.belvo.com"

response = requests.get(
    f"{base_url}/api/accounts/",
    auth=(secret_id, secret_password),
)

print(f"Status: {response.status_code}")
print(json.dumps(response.json(), indent=2))
