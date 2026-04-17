"""
Portfolio service layer for Argentina SMB risk monitoring.

Entry points:
    build_portfolio(merchants)          → portfolio-level summary + per-merchant rows
    build_merchant_detail(link_id, ...) → single merchant full metrics + 30/60/90d trend

Public constants:
    _CASE_EVENT_LABELS   — human-readable labels for case/action event types
    _HIGH_RISK_ACTIONS   — frozenset of action strings that require elevated review cadence
"""
from datetime import date, timedelta
from typing import Optional

from argentina_config import (
    ACTION_LABELS,
    ACTION_STATUS_COLORS,
    ALERT_THRESHOLDS,
    MODEL_NAME,
    LOOKBACK_WINDOWS,
    REFRESH_MODE,
    REVIEW_CADENCE_DAYS,
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


_HIGH_RISK_ACTIONS = frozenset({"reduce_exposure", "review_now"})

_CASE_EVENT_LABELS: dict[str, str] = {
    "flag_raised":                 "Case Flagged",
    "analyst_reviewed":            "Analyst Reviewed",
    "recommendation_confirmed":    "Recommendation Confirmed",
    "no_action_taken":             "No Action Taken",
    "reduce_exposure_recommended": "Reduce Exposure Recommended",
    "topup_candidate_flagged":     "Top-Up Candidate Flagged",
}

_MODEL_META = {
    "name":             MODEL_NAME,
    "lookback_windows": LOOKBACK_WINDOWS,
    "refresh_mode":     REFRESH_MODE,
}


def _build_risk_history(transactions: list) -> list[dict]:
    """
    Derive a state-change audit trail from the 30/60/90d windows.
    Consecutive identical states are collapsed into one entry.

    Note: this is an approximation derived from windowed snapshots.
    Production should read from a persisted state-change events table.
    """
    today = date.today()
    snapshots = []
    for window in (90, 60, 30):
        metrics = extract_argentina_features_window(transactions, window)
        scored  = score_argentina(metrics)
        lights  = scored["metric_lights"]
        drivers = _top_risk_drivers(metrics, lights)
        reason  = drivers[0]["description"] if drivers else "All metrics within normal range"
        as_of   = today.isoformat() if window == 30 else (today - timedelta(days=window)).isoformat()
        snapshots.append({
            "date":       as_of,
            "event_type": "state",
            "action":     scored["action"],
            "label":      scored["action"].replace("_", " ").title(),
            "reason":     reason,
            "period":     "Current (last 30d)" if window == 30 else f"~{window} days ago",
        })

    # Emit an entry only when the action changes; always include current snapshot.
    history: list[dict] = []
    for i, snap in enumerate(snapshots):
        prev_action = snapshots[i - 1]["action"] if i > 0 else None
        if snap["action"] != prev_action:
            history.append(snap)

    if not history or history[-1]["period"] != "Current (last 30d)":
        history.append(snapshots[-1])

    return history


_SECTOR_DET_THRESHOLD = -0.10   # amber-level; sectors averaging below this are "deteriorating"


def _compute_escalation(row: dict, override: Optional[dict]) -> tuple:
    """
    Return (needs_escalation, escalation_reason).
    Rules evaluated in priority order — first match wins.
    """
    # Rule 1: high-risk merchant with overdue review
    if row["action"] in _HIGH_RISK_ACTIONS and row["review_overdue_days"] > 0:
        return True, (
            f"High-risk merchant overdue for review by {row['review_overdue_days']}d"
        )

    # Rule 2: analyst override applied to a high-risk merchant
    # Check original_recommendation so overridden-but-still-dangerous cases surface.
    if override:
        orig = override.get("original_recommendation", row["action"])
        if orig in _HIGH_RISK_ACTIONS:
            return True, f"Analyst override active on high-risk merchant ({orig})"

    # Rule 3: two or more critical alerts
    critical_count = sum(1 for a in row["alerts"] if a["severity"] == "critical")
    if critical_count >= 2:
        return True, f"{critical_count} critical alerts require immediate attention"

    return False, None


def _review_fields(action: str, review_state: Optional[dict]) -> dict:
    """
    Compute review schedule fields from risk state and last review date.
    review_state keys: review_status, owner, analyst_note, last_review_date (ISO or None).
    """
    rs      = review_state or {}
    cadence = REVIEW_CADENCE_DAYS.get(action, 30)
    today   = date.today()
    last    = rs.get("last_review_date")

    if last:
        next_review  = date.fromisoformat(last) + timedelta(days=cadence)
    else:
        next_review  = today - timedelta(days=1)   # never reviewed → already overdue

    overdue = max(0, (today - next_review).days)

    return {
        "review_status":       rs.get("review_status", "unreviewed"),
        "owner":               rs.get("owner"),
        "analyst_note":        rs.get("analyst_note"),
        "next_review_date":    next_review.isoformat(),
        "review_overdue_days": overdue,
    }


def build_merchant_row(
    link_id: str,
    name: str,
    sector: str,
    bank: str,
    transactions: list,
    review_state: Optional[dict] = None,
    override: Optional[dict] = None,
) -> dict:
    """Compute all metrics for one merchant and return a portfolio row."""
    metrics = extract_argentina_features(transactions)
    scored  = score_argentina(metrics)
    action  = scored["action"]
    lights  = scored["metric_lights"]

    row = {
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
        **_review_fields(action, review_state),
    }

    if override:
        row["override"] = {
            "original_recommendation": override.get("original_recommendation", action),
            "current_recommendation":  override.get("current_recommendation", action),
            "override_reason":         override.get("override_reason", ""),
            "override_timestamp":      override.get("override_timestamp", ""),
            "override_by":             override.get("override_by", ""),
        }

    needs_esc, esc_reason = _compute_escalation(row, override)
    row["needs_escalation"]  = needs_esc
    row["escalation_reason"] = esc_reason

    return row


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
            m["link_id"], m["name"], m["sector"], m["bank"], m["transactions"],
            review_state=m.get("review_state"),
            override=m.get("override"),
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

    # Migration stats (last 30d)
    improved_count  = sum(1 for r in rows if r["deterioration_index"] > 0.05)
    deteriorated    = sum(1 for r in rows if r["deterioration_index"] < -0.10)
    new_high_risk   = 0
    for m_data, row in zip(merchants, rows):
        if row["action"] in _HIGH_RISK_ACTIONS:
            prior_metrics = extract_argentina_features_window(m_data["transactions"], 60)
            if score_argentina(prior_metrics)["action"] not in _HIGH_RISK_ACTIONS:
                new_high_risk += 1

    # Review workflow aggregates
    unreviewed_count   = sum(1 for r in rows if r["review_status"] == "unreviewed")
    overdue_count      = sum(1 for r in rows if r["review_overdue_days"] > 0)
    high_risk_by_sector: dict[str, int] = {}
    for r in rows:
        if r["action"] in _HIGH_RISK_ACTIONS:
            s = r.get("sector", "other")
            high_risk_by_sector[s] = high_risk_by_sector.get(s, 0) + 1
    high_risk_by_sector = dict(
        sorted(high_risk_by_sector.items(), key=lambda kv: -kv[1])
    )

    # Escalation + open-case aggregates
    escalated_count = sum(1 for r in rows if r["needs_escalation"])
    open_case_count = sum(
        1 for r in rows
        if r["action"] in _HIGH_RISK_ACTIONS
        and r["review_status"] in ("unreviewed", "in_review")
    )

    # Deteriorating sectors: sectors whose average deterioration_index < threshold
    sector_det_vals: dict[str, list] = {}
    for r in rows:
        sector_det_vals.setdefault(r.get("sector", "other"), []).append(
            r["deterioration_index"]
        )
    deteriorating_by_sector = {
        s: round(sum(vals) / len(vals), 3)
        for s, vals in sector_det_vals.items()
        if sum(vals) / len(vals) < _SECTOR_DET_THRESHOLD
    }
    deteriorating_by_sector = dict(
        sorted(deteriorating_by_sector.items(), key=lambda kv: kv[1])   # worst first
    )

    return {
        "model":                      _MODEL_META,
        "last_refreshed":             date.today().isoformat(),
        "merchant_count":              n,
        "action_counts":               action_counts,
        "status_color_counts":         status_color_counts,
        "avg_deterioration_index":     avg_deterioration,
        "avg_real_cash_coverage":      avg_cash_coverage,
        "avg_fx_mismatch_exposure":    avg_fx_mismatch,
        "merchants_worsened_last_30d": deteriorated,
        "improved_count_30d":          improved_count,
        "deteriorated_count_30d":      deteriorated,
        "new_high_risk_30d":           new_high_risk,
        "unreviewed_count":            unreviewed_count,
        "overdue_review_count":        overdue_count,
        "high_risk_by_sector":         high_risk_by_sector,
        "escalated_count":             escalated_count,
        "open_case_count":             open_case_count,
        "deteriorating_by_sector":     deteriorating_by_sector,
        "merchants":                   rows,
    }


def build_merchant_detail(
    link_id: str,
    name: str,
    sector: str,
    bank: str,
    transactions: list,
    review_state: Optional[dict] = None,
    override: Optional[dict] = None,
    case_log: Optional[list] = None,
) -> dict:
    """
    Single-merchant response with full metrics + 30/60/90d trend windows.
    Used by GET /merchant/{id}/data.
    """
    row = build_merchant_row(link_id, name, sector, bank, transactions,
                             review_state=review_state, override=override)

    trend: dict[str, dict] = {}
    for window in (30, 60, 90):
        trend[f"w{window}d"] = extract_argentina_features_window(transactions, window)

    history = _build_risk_history(transactions)

    # Inject override event into timeline when present
    if override:
        ts    = override.get("override_timestamp", date.today().isoformat())
        ev_dt = ts[:10]   # YYYY-MM-DD
        history.append({
            "date":       ev_dt,
            "action":     override.get("current_recommendation", row["action"]),
            "label":      "Analyst Override",
            "reason":     f"Analyst override by {override.get('override_by', 'unknown')}: "
                          f"{override.get('override_reason', '')}",
            "period":     "Override",
            "event_type": "override",
        })
        history.sort(key=lambda e: e["date"])

    # Merge case/action events into the timeline
    for ev in (case_log or []):
        history.append({
            "date":       ev["date"],
            "event_type": ev["event_type"],
            "label":      _CASE_EVENT_LABELS.get(ev["event_type"], ev["event_type"]),
            "action":     row["action"],   # context only; not a state change
            "reason":     ev.get("note", ""),
            "period":     ev["date"],
            "analyst":    ev.get("analyst"),
        })
    history.sort(key=lambda e: e["date"])

    return {
        **row,
        "model":          _MODEL_META,
        "last_refreshed": date.today().isoformat(),
        "trend_windows":  trend,
        "risk_history":   history,
        "case_log":       case_log or [],
    }
