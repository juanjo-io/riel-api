"""
Create three Belvo sandbox links for erebor_mx_retail and print their link IDs.
Usage: python scripts/create_sandbox_links.py
Requires BELVO_SECRET_ID and BELVO_SECRET_PASSWORD in .env or environment.
"""

import os
import sys

from dotenv import load_dotenv
from belvo.client import Client
from belvo.enums import AccessMode

load_dotenv()

SECRET_ID  = os.getenv("BELVO_SECRET_ID")
SECRET_PWD = os.getenv("BELVO_SECRET_PASSWORD")

if not SECRET_ID or not SECRET_PWD:
    sys.exit("ERROR: BELVO_SECRET_ID and BELVO_SECRET_PASSWORD must be set.")

client = Client(SECRET_ID, SECRET_PWD, "https://sandbox.belvo.com")

INSTITUTION = "erebor_mx_retail"

MERCHANTS = [
    {"handle": "johndoe",  "username": "johndoe",  "password": "supersecret"},
    {"handle": "janedoe",  "username": "janedoe",  "password": "supersecret"},
    {"handle": "rosedoe",  "username": "rosedoe",  "password": "supersecret"},
]

print(f"Creating {len(MERCHANTS)} sandbox links for {INSTITUTION}...\n")

for m in MERCHANTS:
    try:
        link = client.Links.create(
            institution=INSTITUTION,
            username=m["username"],
            password=m["password"],
            access_mode=AccessMode.SINGLE,
        )
        link_id = link["id"] if isinstance(link, dict) else link[0]["id"]
        print(f"  {m['handle']:10s}  link_id = {link_id}")
    except Exception as e:
        print(f"  {m['handle']:10s}  ERROR: {e}")

print("\nDone.")
