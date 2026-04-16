import os
from prometeo import Client
from datetime import datetime

api_key = "nnCNb3nB8mike3DtKSFUWKopJRAnygJWBLdSbmOMbHOfZehHIbY8XWCTKln0nuPV"

client = Client(api_key, environment='sandbox')

session = client.banking.login(
    provider='test',
    username='12345',
    password='gfdsa'
)

accounts = session.get_accounts()
for account in accounts:
    print(account.number, '-', account.name)

movements = accounts[0].get_movements(
    datetime(2024, 1, 1),
    datetime(2024, 3, 31)
)
for m in movements:
    print(m.detail, m.debit, m.credit)
