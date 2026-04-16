from datetime import datetime, date
from collections import defaultdict


def _get_reference_date(transactions: list) -> date:
    dates = []
    for t in transactions:
        raw = t.get("value_date") or t.get("transaction_date") or t.get("date") or ""
        try:
            dates.append(datetime.strptime(raw[:10], "%Y-%m-%d").date())
        except (ValueError, TypeError):
            pass
    return max(dates) if dates else date.today()


def _days_ago(t: dict, reference: date) -> int:
    raw = t.get("value_date") or t.get("transaction_date") or t.get("date") or ""
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        return (reference - d).days
    except (ValueError, TypeError):
        return 9999


def extract_argentina_features(transactions: list, account_balance: float = 0.0) -> dict:
    """
    Extract 5 Argentina-specific risk metrics from transaction history.

    Returns dict with:
        survival_runway_days    — estimated days cash can cover burn at current rate
        real_cash_coverage      — 90d inflows / contractual (recurring) outflows
        fx_mismatch_exposure    — share of 90d outflows in USD/EUR (0–1)
        revenue_concentration   — top-3 counterparty share of 90d inflows (0–1)
        deterioration_index     — trend: +1 improving, -1 deteriorating
    """
    if not transactions:
        return {
            "survival_runway_days": 0,
            "real_cash_coverage": 0.0,
            "fx_mismatch_exposure": 0.0,
            "revenue_concentration": 1.0,
            "deterioration_index": 0.0,
        }

    today = _get_reference_date(transactions)

    txs_30d    = [t for t in transactions if _days_ago(t, today) <= 30]
    txs_31_60d = [t for t in transactions if 30 < _days_ago(t, today) <= 60]
    txs_90d    = [t for t in transactions if _days_ago(t, today) <= 90]

    # ── Survival Runway ──────────────────────────────────────────────────────
    outflows_30d = [-t["amount"] for t in txs_30d if (t.get("amount") or 0) < 0]
    inflows_30d  = [ t["amount"] for t in txs_30d if (t.get("amount") or 0) > 0]

    daily_burn = sum(outflows_30d) / 30 if outflows_30d else 0

    if account_balance > 0:
        current_cash = account_balance
    else:
        current_cash = max(0.0, sum(inflows_30d) - sum(outflows_30d))

    if daily_burn > 0:
        survival_runway_days = int(min(current_cash / daily_burn, 365))
    else:
        survival_runway_days = 365

    # ── Real Cash Coverage ───────────────────────────────────────────────────
    outflow_counter: dict[str, list] = defaultdict(list)
    for t in txs_90d:
        if (t.get("amount") or 0) < 0 and t.get("counterparty_name"):
            outflow_counter[t["counterparty_name"]].append(-(t["amount"]))

    contractual_outflows = sum(
        sum(amounts)
        for amounts in outflow_counter.values()
        if len(amounts) >= 2
    )
    total_inflows_90d = sum(t["amount"] for t in txs_90d if (t.get("amount") or 0) > 0)

    if contractual_outflows > 0:
        real_cash_coverage = round(total_inflows_90d / contractual_outflows, 3)
    else:
        real_cash_coverage = 3.0

    # ── FX Mismatch Exposure ─────────────────────────────────────────────────
    FX_KEYWORDS = {"usd", "dolar", "dolares", "eur", "euro", "euros"}
    total_outflows_90d = sum(-(t["amount"]) for t in txs_90d if (t.get("amount") or 0) < 0)
    fx_outflows = 0.0

    for t in txs_90d:
        if (t.get("amount") or 0) >= 0:
            continue
        currency = (t.get("currency") or "").upper()
        desc = (t.get("description") or "").lower()
        if currency in ("USD", "EUR") or any(kw in desc for kw in FX_KEYWORDS):
            fx_outflows += -(t["amount"])

    fx_mismatch_exposure = round(fx_outflows / total_outflows_90d, 3) if total_outflows_90d > 0 else 0.0

    # ── Revenue Concentration ────────────────────────────────────────────────
    inflow_by_cp: dict[str, float] = defaultdict(float)
    for t in txs_90d:
        if (t.get("amount") or 0) > 0 and t.get("counterparty_name"):
            inflow_by_cp[t["counterparty_name"]] += t["amount"]

    if inflow_by_cp and total_inflows_90d > 0:
        top3 = sum(sorted(inflow_by_cp.values(), reverse=True)[:3])
        revenue_concentration = round(top3 / total_inflows_90d, 3)
    else:
        revenue_concentration = 1.0

    # ── Deterioration Index ──────────────────────────────────────────────────
    def net(txs):
        return (
            sum(t["amount"] for t in txs if (t.get("amount") or 0) > 0)
            - sum(-(t["amount"]) for t in txs if (t.get("amount") or 0) < 0)
        )

    net_30d    = net(txs_30d)
    net_31_60d = net(txs_31_60d)

    if net_31_60d != 0:
        raw = (net_30d - net_31_60d) / abs(net_31_60d)
        deterioration_index = round(max(-1.0, min(1.0, raw)), 3)
    elif net_30d > 0:
        deterioration_index = 1.0
    elif net_30d < 0:
        deterioration_index = -1.0
    else:
        deterioration_index = 0.0

    return {
        "survival_runway_days": survival_runway_days,
        "real_cash_coverage": real_cash_coverage,
        "fx_mismatch_exposure": fx_mismatch_exposure,
        "revenue_concentration": revenue_concentration,
        "deterioration_index": deterioration_index,
    }
