import json

with open("sample_transactions.json") as f:
    transactions = json.load(f)

print(f"Total transactions loaded: {len(transactions)}\n")
print("=== First 5 transactions ===")
for i, t in enumerate(transactions[:5]):
    print(f"\n--- Transaction {i+1} ---")
    print(json.dumps(t, indent=2))
