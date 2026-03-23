def calculate_riel_score(features: dict) -> dict:
    payment_consistency = features.get("payment_consistency", 0.0)
    counterparty_diversity = features.get("counterparty_diversity", 0)
    merchant_ratio = features.get("merchant_ratio", 0.0)
    income_stability = features.get("income_stability", 0.0)
    repayment_proxy = features.get("repayment_proxy", False)
    tenure_days = features.get("tenure_days", 0)

    score = (
        payment_consistency * 30
        + min(counterparty_diversity / 20, 1.0) * 20
        + merchant_ratio * 15
        + income_stability * 20
        + (10 if repayment_proxy else 0)
        + min(tenure_days / 180, 1.0) * 5
    )

    riel_score = round(score)

    if riel_score >= 70:
        recommendation = "approve"
        suggested_limit_cop = 300000
    elif riel_score >= 50:
        recommendation = "review"
        suggested_limit_cop = 150000
    else:
        recommendation = "decline"
        suggested_limit_cop = 0

    return {
        "riel_score": riel_score,
        "recommendation": recommendation,
        "suggested_limit_cop": suggested_limit_cop,
    }
