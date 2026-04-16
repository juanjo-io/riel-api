"""
Portfolio service layer for Argentina SMB risk monitoring.

Entry points:
    build_portfolio(merchants)          → portfolio-level summary + per-merchant rows
    build_merchant_detail(link_id, ...) → single merchant full metrics + 30/60/90d trend
"""
from datetime import date

from argentina_config import (
    ACTION_LABELS,
    ACTION_STATUS_COLORS,
    ALERT_THRESHOLDS,
)
from argentina_features import extract_argentina_features, extract_argentina_features_window
from argentina_scorer import score_argentina


# ── Risk driver labels ────────────────────────────────────────────────────────
# Each key maps to {color: human-readable template}.
# Templates use Python str.format() with a single positional arg `v`.
_DRIVER_LABELS: dict[str, dict[str, str]] = {
    "survival_runway": {
        "red":   "Runway critical: {v} days of cash remaining",
        "amber": "Runway tight: {v} days — monitor closely",
    },
    "real_cash_coverage": {
        "red":   "Coverage insufficient: {v:.2f}× (inflows may not cover obligations)",
        "amber": "Coverage thin: {v:.2f}× (below 1.5× target)",
    },
    "fx_mismatch": {
        "red":   "High FX exposure: {v:.0%} of costs in USD/EUR",
        "amber": "Moderate FX exposure: {v:.0%} of costs in foreign currency",
    },
    "revenue_concentration": {
        "red":   "Revenue highly concentrated: top-3 clients = {v:.0%}",
        "amber": "Revenue moderately concentrated: top-3 clients = {v:.0%}",
    },
    "deterioration": {
        "red":   "Business deteriorating: index {v:+.2f} (significant 30-day decline)",
        "amber": "Trend weakening: index {v:+.2f} — watch next 30 days",
    },
}

# Map from lights key → metrics key (for retrieving the value to format)
_METRIC_KEY_MAP = {
    "survival_runway":       "survival_runway_days",
    "real_cash_coverage":    "real_cash_coverage",
    "fx_mismatch":           "fx_mismatch_exposure",
    "revenue_concentration": "revenue_concentration",
    "deterioration":         "deterioration_index",
}


def _top_risk_drivers(metrics: dict, lights: dict) -> list[dict]:
    """
    Return up to 3 risk drivers ordered by severity (red first, then amber).
    Green metrics are excluded — they are not risk drivers.
    """
    color_rank = {"red": 0, "amber": 1, "green": 2}
    drivers = []

    for light_key, metric_key in _METRIC_KEY_MAP.items():
        color = lights[light_key]
        if color == "green":
            continue

        value = metrics[metric_key]
        template = _DRIVER_LABELS.get(light_key, {}).get(color, f"{metric_key}: {value}")
        try:
            description = template.format(v=value)
        except (KeyError, ValueError):
            description = f"{metric_key}: {value}"

        drivers.append({
            "metric":      metric_key,
            "light":       color,
            "value":       value,
            "description": description,
        })

    drivers.sort(key=lambda d: color_rank[d["light"]])
    return drivers[:3]


def _generate_alerts(metrics: dict) -> list[dict]:
    """Return structured alerts for any metric that breaches a critical threshold."""
    alerts = []
    t = ALERT_THRESHOLDS

    if metrics["survival_runway_days"] <= t["runway_critical_days"]:
        alerts.append({
            "type":     "runway_critical",
            "severity": "critical",
            "message":  (
                f"Survival runway is {metrics['survival_runway_days']} days — "
                f"at or below the {t['runway_critical_days']}-day threshold"
            ),
        })

    if metrics["real_cash_coverage"] < t["coverage_critical"]:
        alerts.append({
            "type":     "coverage_insufficient",
            "severity": "critical",
            "message":  (
                f"Cash coverage {metrics['real_cash_coverage']:.2f}× is below 1.0 — "
                "inflows may not cover contractual obligations"
            ),
        })

    if metrics["fx_mismatch_exposure"] >= t["fx_high"]:
        alerts.append({
            "type":     "fx_high",
            "severity": "warning",
            "message":  (
                f"FX mismatch {metrics['fx_mismatch_exposure']:.0%} of outflows "
                "in foreign currency — ARS depreciation risk"
            ),
        })

    if metrics["revenue_concentration"] >= t["concentration_high"]:
        alerts.append({
            "type":     "concentration_high",
            "severity": "warning",
            "message":  (
                f"Top-3 clients = {metrics['revenue_concentration']:.0%} of revenue — "
                "high counterparty dependency"
            ),
        })

    if metrics["deterioration_index"] <= t["deterioration_severe"]:
        alerts.append({
            "type":     "deterioration_severe",
            "severity": "critical",
            "message":  (
                f"Deterioration index {metrics['deterioration_index']:+.2f} — "
                "significant decline in last 30 days vs prior period"
            ),
        })

    return alerts


def build_merchant_row(
    link_id: str,
    name: str,
    sector: str,
    bank: str,
    transactions: list,
) -> dict:
    """Compute all metrics for one merchant and return a portfolio row."""
    metrics = extract_argentina_features(transactions)
    scored  = score_argentina(metrics)
    action  = scored["action"]
    lights  = scored["metric_lights"]

    return {
        "merchant_id":             link_id,
        "name":                    name,
        "sector":                  sector,
        "bank":                    bank,
        "action":                  action,
        "status_color":            ACTION_STATUS_COLORS[action],
        "action_label":            ACTION_LABELS[action],
        "survival_runway_days":    metrics["survival_runway_days"],
        "real_cash_coverage":      metrics["real_cash_coverage"],
        "fx_mismatch_exposure":    metrics["fx_mismatch_exposure"],
        "revenue_concentration":   metrics["revenue_concentration"],
        "deterioration_index":     metrics["deterioration_index"],
        "metric_lights":           lights,
        "top_risk_drivers":        _top_risk_drivers(metrics, lights),
        "alerts":                  _generate_alerts(metrics),
        "last_updated":            date.today().isoformat(),
    }


def build_portfolio(merchants: list) -> dict:
    """
    Aggregate all merchants into a portfolio-level response.

    Parameters
    ----------
    merchants : list of dicts with keys:
        link_id, name, sector, bank, transactions
    """
    rows = [
        build_merchant_row(
            m["link_id"], m["name"], m["sector"], m["bank"], m["transactions"]
        )
        for m in merchants
    ]

    n = len(rows)

    action_counts: dict[str, int] = {}
    for r in rows:
        action_counts[r["action"]] = action_counts.get(r["action"], 0) + 1

    status_color_counts: dict[str, int] = {}
    for r in rows:
        status_color_counts[r["status_color"]] = (
            status_color_counts.get(r["status_color"], 0) + 1
        )

    avg_deterioration  = round(sum(r["deterioration_index"]    for r in rows) / n, 3) if n else 0.0
    avg_cash_coverage  = round(sum(r["real_cash_coverage"]     for r in rows) / n, 3) if n else 0.0
    avg_fx_mismatch    = round(sum(r["fx_mismatch_exposure"]   for r in rows) / n, 3) if n else 0.0
    merchants_worsened = sum(1 for r in rows if r["deterioration_index"] < -0.10)

    return {
        "merchant_count":              n,
        "action_counts":               action_counts,
        "status_color_counts":         status_color_counts,
        "avg_deterioration_index":     avg_deterioration,
        "avg_real_cash_coverage":      avg_cash_coverage,
        "avg_fx_mismatch_exposure":    avg_fx_mismatch,
        "merchants_worsened_last_30d": merchants_worsened,
        "merchants":                   rows,
    }


def build_merchant_detail(
    link_id: str,
    name: str,
    sector: str,
    bank: str,
    transactions: list,
) -> dict:
    """
    Single-merchant response with full metrics + 30/60/90d trend windows.
    Used by GET /merchant/{id}/data.
    """
    row = build_merchant_row(link_id, name, sector, bank, transactions)

    trend: dict[str, dict] = {}
    for window in (30, 60, 90):
        trend[f"w{window}d"] = extract_argentina_features_window(transactions, window)

    return {**row, "trend_windows": trend}
