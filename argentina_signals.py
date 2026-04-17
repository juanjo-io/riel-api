"""
External signal fetch for the Argentina agentic refresh flow.
Phase 3 v0 (riel_argentina_v0_3) — mock only, no live API calls.

In production, replace get_external_signal() with a real FX data source
(e.g. BCRA official rate, Dolarito informal index, or an x402-gated aggregator).
apply_fx_signal() and build_refresh_event() are source-agnostic.

Signal lifecycle:
  1. POST /argentina/merchant/{link_id}/refresh  (manual, lender-triggered)
  2. get_external_signal(link_id)                (returns mock rate snapshot)
  3. apply_fx_signal(txs, base_metrics, signal)  (recomputes FX-affected metrics)
  4. build_refresh_event(...)                    (assembles timeline entry)
"""
from datetime import date

from argentina_config import FX_KEYWORDS
from argentina_features import _get_reference_date, _days_ago


# ── Mock signal table ─────────────────────────────────────────────────────────
# Deterministic by link_id. Rates in ARS/USD.
# macro_stress: "low" | "moderate" | "high"
_MOCK_SIGNALS: dict = {
    # Ferretería López — 15% FX exposure from USD tool imports
    "a1b2c3d4-0005-0005-0005-000000000005": {
        "base_rate": 900, "new_rate": 985,
        "macro_stress": "moderate",
    },
    # Almacén El Toro — high FX exposure (foreign-branded goods)
    "a1b2c3d4-0006-0006-0006-000000000006": {
        "base_rate": 900, "new_rate": 960,
        "macro_stress": "moderate",
    },
    # Librería Central — mild stress (imported stationery)
    "a1b2c3d4-0008-0008-0008-000000000008": {
        "base_rate": 900, "new_rate": 935,
        "macro_stress": "low",
    },
}

_DEFAULT_SIGNAL: dict = {
    "base_rate": 900, "new_rate": 920,
    "macro_stress": "low",
}

_SOURCE = "BCRA informal reference (mock — Phase 3 v0)"


def get_external_signal(link_id: str) -> dict:
    """
    Return a mock FX/macro signal for the given merchant.
    Deterministic by link_id. No external API is called in Phase 3 v0.
    """
    raw = _MOCK_SIGNALS.get(link_id, _DEFAULT_SIGNAL)
    factor = round(raw["new_rate"] / raw["base_rate"], 6)
    return {
        "signal_type":         "fx_rate_snapshot",
        "fx_adjustment_factor": factor,
        "base_rate_ars_usd":   raw["base_rate"],
        "new_rate_ars_usd":    raw["new_rate"],
        "rate_change_pct":     round((factor - 1) * 100, 2),
        "macro_stress":        raw["macro_stress"],
        "source":              _SOURCE,
        "as_of":               date.today().isoformat(),
    }


def apply_fx_signal(
    transactions: list,
    base_metrics: dict,
    signal: dict,
) -> dict:
    """
    Recompute FX-affected metrics given an external FX rate adjustment.

    Only fx_mismatch_exposure is updated. The adjustment models ARS depreciation:
    if ARS/USD rises 900 → 985, FX-denominated outflows cost 9.4% more in ARS,
    increasing the fx_mismatch_exposure ratio.

    All other metrics are carried from base_metrics unchanged.

    Returns a full metrics dict (safe to pass directly to score_argentina).
    """
    factor = signal["fx_adjustment_factor"]

    if not transactions or factor == 1.0:
        return base_metrics.copy()

    # Re-extract raw FX/total outflow components (90d window)
    ref     = _get_reference_date(transactions)
    txs_90d = [t for t in transactions if _days_ago(t, ref) <= 90]

    total_outflows_90d = sum(
        -(t["amount"]) for t in txs_90d if (t.get("amount") or 0) < 0
    )
    fx_outflows = 0.0
    for t in txs_90d:
        if (t.get("amount") or 0) >= 0:
            continue
        currency = (t.get("currency") or "").upper()
        desc     = (t.get("description") or "").lower()
        if currency in ("USD", "EUR") or any(kw in desc for kw in FX_KEYWORDS):
            fx_outflows += -(t["amount"])

    if total_outflows_90d == 0 or fx_outflows == 0:
        # No FX exposure on this merchant — signal has no metric impact
        return base_metrics.copy()

    # Inflate FX outflows by the ARS depreciation factor
    new_fx_outflows    = fx_outflows * factor
    new_total_outflows = total_outflows_90d - fx_outflows + new_fx_outflows
    new_fx_mismatch    = (
        round(new_fx_outflows / new_total_outflows, 3)
        if new_total_outflows > 0
        else 0.0
    )

    updated = base_metrics.copy()
    updated["fx_mismatch_exposure"] = new_fx_mismatch
    return updated


def build_refresh_event(
    signal: dict,
    base_metrics: dict,
    updated_metrics: dict,
    base_action: str,
    updated_action: str,
) -> dict:
    """
    Assemble a risk_history timeline entry for an agent_refresh.
    """
    old_fx = base_metrics["fx_mismatch_exposure"]
    new_fx = updated_metrics["fx_mismatch_exposure"]
    fx_changed = abs(new_fx - old_fx) > 0.001

    rate_part = (
        f"FX rate {signal['base_rate_ars_usd']} → {signal['new_rate_ars_usd']} ARS/USD "
        f"(+{signal['rate_change_pct']:.1f}%, {signal['macro_stress']} macro stress)"
    )
    metric_part = (
        f"FX mismatch {old_fx:.1%} → {new_fx:.1%}"
        if fx_changed
        else "No FX-denominated outflows — signal had no metric impact"
    )
    rec_part = (
        f"Recommendation changed: {base_action} → {updated_action}"
        if base_action != updated_action
        else f"Recommendation unchanged: {base_action}"
    )

    return {
        "date":       date.today().isoformat(),
        "event_type": "agent_refresh",
        "label":      "Agent Refresh (FX update)",
        "action":     updated_action,
        "reason":     f"{rate_part}. {metric_part}. {rec_part}.",
        "period":     f"Refreshed {date.today().isoformat()}",
        "signal":     signal,
    }
