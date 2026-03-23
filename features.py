from datetime import datetime, timedelta
from collections import defaultdict
import statistics


def extract_features(transactions: list) -> dict:
    if not transactions:
        return {
            "payment_consistency": 0.0,
            "counterparty_diversity": 0,
            "merchant_ratio": 0.0,
            "income_stability": 0.0,
            "repayment_proxy": False,
            "tenure_days": 0,
        }

    MERCHANT_CATEGORIES = {"merchant", "commerce", "food", "groceries", "food & drink", "shopping"}

    dates = []
    inflow_amounts = []
    outflow_by_counterparty = defaultdict(int)
    counterparties = set()
    merchant_count = 0

    for t in transactions:
        # Parse date
        raw_date = t.get("value_date") or t.get("transaction_date") or t.get("date")
        if raw_date:
            try:
                dates.append(datetime.strptime(raw_date[:10], "%Y-%m-%d").date())
            except ValueError:
                pass

        amount = t.get("amount", 0) or 0
        counterparty = t.get("counterparty_name") or t.get("counterparty", {}).get("name", "")
        category = (t.get("category") or "").strip()

        if counterparty:
            counterparties.add(counterparty)

        if amount > 0:
            inflow_amounts.append(amount)
        elif amount < 0:
            if counterparty:
                outflow_by_counterparty[counterparty] += 1

        if category.lower() in MERCHANT_CATEGORIES:
            merchant_count += 1

    # tenure_days
    tenure_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0

    # payment_consistency: proportion of last 13 weeks with at least one outgoing payment
    if dates:
        reference_date = max(dates)
        weeks_with_payment = 0
        for week in range(13):
            week_end = reference_date - timedelta(weeks=week)
            week_start = week_end - timedelta(weeks=1)
            has_payment = any(
                week_start <= d <= week_end
                for t, d in zip(transactions, dates)
                if (t.get("amount", 0) or 0) < 0
            )
            if has_payment:
                weeks_with_payment += 1
        payment_consistency = round(weeks_with_payment / 13, 4)
    else:
        payment_consistency = 0.0

    # counterparty_diversity
    counterparty_diversity = len(counterparties)

    # merchant_ratio
    merchant_ratio = round(merchant_count / len(transactions), 4) if transactions else 0.0

    # income_stability: 1 - CV of inflows, clamped to [0, 1]
    if len(inflow_amounts) >= 2:
        mean = statistics.mean(inflow_amounts)
        stdev = statistics.stdev(inflow_amounts)
        cv = stdev / mean if mean > 0 else 0.0
        income_stability = round(max(0.0, min(1.0, 1 - cv)), 4)
    elif len(inflow_amounts) == 1:
        income_stability = 1.0
    else:
        income_stability = 0.0

    # repayment_proxy: any counterparty with 3+ outgoing transactions
    repayment_proxy = any(count >= 3 for count in outflow_by_counterparty.values())

    return {
        "payment_consistency": payment_consistency,
        "counterparty_diversity": counterparty_diversity,
        "merchant_ratio": merchant_ratio,
        "income_stability": income_stability,
        "repayment_proxy": repayment_proxy,
        "tenure_days": tenure_days,
    }
