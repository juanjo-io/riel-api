import json
from features import extract_features
from scorer import calculate_riel_score

with open("sample_transactions.json") as f:
    transactions = json.load(f)

features = extract_features(transactions)
result = calculate_riel_score(features)

print("=" * 45)
print("       RIEL CREDIT SCORING PIPELINE")
print("=" * 45)

print(f"\nTransactions loaded: {len(transactions)}")

print("\n--- Features ---")
print(f"  payment_consistency   : {features['payment_consistency']:.4f}")
print(f"  counterparty_diversity: {features['counterparty_diversity']}")
print(f"  merchant_ratio        : {features['merchant_ratio']:.4f}")
print(f"  income_stability      : {features['income_stability']:.4f}")
print(f"  repayment_proxy       : {features['repayment_proxy']}")
print(f"  tenure_days           : {features['tenure_days']}")

print("\n--- Score Result ---")
print(f"  Riel Score      : {result['riel_score']} / 100")
print(f"  Recommendation  : {result['recommendation'].upper()}")
print(f"  Suggested Limit : COP {result['suggested_limit_cop']:,}")

print("\n" + "=" * 45)
