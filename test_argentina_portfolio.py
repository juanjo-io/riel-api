"""
Tests for the Argentina portfolio service layer.
Run: python3 test_argentina_portfolio.py
"""
from providers.mock_provider import MockProvider, MOCK_MERCHANTS_AR
from argentina_features import extract_argentina_features
from argentina_scorer import score_argentina
from argentina_portfolio import (
    build_portfolio,
    build_merchant_row,
    build_merchant_detail,
    _top_risk_drivers,
    _generate_alerts,
    _compute_escalation,
    _CASE_EVENT_LABELS,
)
from argentina_config import ALERT_THRESHOLDS
from argentina_signals import get_external_signal, apply_fx_signal, build_refresh_event
from providers.mock_provider import (
    MOCK_REVIEW_STATE_AR, MOCK_OVERRIDES_AR, MOCK_CASE_LOG_AR,
)

_PASS = "\033[92m✓\033[0m"
_FAIL = "\033[91m✗\033[0m"

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {_PASS} {label}")
    else:
        print(f"  {_FAIL} {label}" + (f" — {detail}" if detail else ""))
    return condition


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_all_merchants(with_review=False):
    """
    Build the merchant list consumed by build_portfolio().
    Pass with_review=True to include review_state and overrides (needed for
    escalation and review-workflow aggregate tests).
    """
    mp = MockProvider()
    result = []
    for lid, meta in MOCK_MERCHANTS_AR.items():
        entry = {
            "link_id":      lid,
            "name":         meta["name"],
            "sector":       meta.get("sector", "other"),
            "bank":         meta.get("bank", ""),
            "transactions": mp.get_transactions(lid),
        }
        if with_review:
            entry["review_state"] = MOCK_REVIEW_STATE_AR.get(lid)
            entry["override"]     = MOCK_OVERRIDES_AR.get(lid)
        result.append(entry)
    return result


# ── Test: expected actions for all 10 merchants ───────────────────────────────

def test_expected_actions():
    print("\ntest_expected_actions")
    EXPECTED = {
        "a1b2c3d4-0004-0004-0004-000000000004": "opportunity",
        "a1b2c3d4-0005-0005-0005-000000000005": "monitor",
        "a1b2c3d4-0006-0006-0006-000000000006": "reduce_exposure",
        "a1b2c3d4-0007-0007-0007-000000000007": "healthy",
        "a1b2c3d4-0008-0008-0008-000000000008": "review_now",
        "a1b2c3d4-0009-0009-0009-000000000009": "monitor",
        "a1b2c3d4-0010-0010-0010-000000000010": "reduce_exposure",
        "a1b2c3d4-0011-0011-0011-000000000011": "healthy",
        "a1b2c3d4-0012-0012-0012-000000000012": "review_now",
        "a1b2c3d4-0013-0013-0013-000000000013": "opportunity",
    }
    mp = MockProvider()
    ok = True
    for lid, expected in EXPECTED.items():
        txs = mp.get_transactions(lid)
        m = extract_argentina_features(txs)
        r = score_argentina(m)
        actual = r["action"]
        name = MOCK_MERCHANTS_AR[lid]["name"]
        ok &= check(f"{name}: {actual}", actual == expected,
                    f"expected {expected}")
    return ok


# ── Test: portfolio aggregation ───────────────────────────────────────────────

def test_portfolio_aggregation():
    print("\ntest_portfolio_aggregation")
    portfolio = build_portfolio(_make_all_merchants())
    ok = True

    ok &= check("merchant_count == 10", portfolio["merchant_count"] == 10)
    ok &= check("merchants list has 10 items", len(portfolio["merchants"]) == 10)

    # Each row must have all 5 metrics
    for row in portfolio["merchants"]:
        for key in ("survival_runway_days", "real_cash_coverage",
                    "fx_mismatch_exposure", "revenue_concentration", "deterioration_index"):
            ok &= check(f"{row['name'][:20]} has {key}", key in row)

    # sector and bank present
    for row in portfolio["merchants"]:
        ok &= check(f"{row['name'][:20]} has sector", bool(row.get("sector")))
        ok &= check(f"{row['name'][:20]} has bank",   bool(row.get("bank")))

    return ok


# ── Test: action counts ───────────────────────────────────────────────────────

def test_action_counts():
    print("\ntest_action_counts")
    portfolio = build_portfolio(_make_all_merchants())
    counts = portfolio["action_counts"]
    ok = True

    ok &= check("opportunity count == 2",     counts.get("opportunity",     0) == 2)
    ok &= check("healthy count == 2",         counts.get("healthy",         0) == 2)
    ok &= check("monitor count == 2",         counts.get("monitor",         0) == 2)
    ok &= check("review_now count == 2",      counts.get("review_now",      0) == 2)
    ok &= check("reduce_exposure count == 2", counts.get("reduce_exposure",  0) == 2)
    ok &= check("total sums to 10",
                sum(counts.values()) == 10, str(counts))

    return ok


# ── Test: portfolio-level aggregates present ──────────────────────────────────

def test_portfolio_aggregates():
    print("\ntest_portfolio_aggregates")
    portfolio = build_portfolio(_make_all_merchants())
    ok = True

    for key in ("avg_deterioration_index", "avg_real_cash_coverage",
                "avg_fx_mismatch_exposure", "merchants_worsened_last_30d",
                "status_color_counts"):
        ok &= check(f"aggregate field '{key}' present", key in portfolio)

    ok &= check("merchants_worsened_last_30d >= 2",
                portfolio["merchants_worsened_last_30d"] >= 2,
                f"got {portfolio['merchants_worsened_last_30d']}")

    return ok


# ── Test: alert generation ────────────────────────────────────────────────────

def test_alert_generation():
    print("\ntest_alert_generation")
    ok = True

    # Runway critical alert
    m_critical = {
        "survival_runway_days": 10,
        "real_cash_coverage":   0.8,
        "fx_mismatch_exposure": 0.4,
        "revenue_concentration": 0.9,
        "deterioration_index":  -0.5,
    }
    alerts = _generate_alerts(m_critical)
    types = {a["type"] for a in alerts}
    ok &= check("runway_critical alert fires",     "runway_critical"      in types)
    ok &= check("coverage_insufficient fires",     "coverage_insufficient" in types)
    ok &= check("fx_high alert fires",             "fx_high"              in types)
    ok &= check("concentration_high fires",        "concentration_high"   in types)
    ok &= check("deterioration_severe fires",      "deterioration_severe" in types)

    # No alerts for a healthy merchant
    m_healthy = {
        "survival_runway_days": 100,
        "real_cash_coverage":   2.0,
        "fx_mismatch_exposure": 0.05,
        "revenue_concentration": 0.3,
        "deterioration_index":  0.2,
    }
    ok &= check("no alerts for healthy merchant",
                len(_generate_alerts(m_healthy)) == 0)

    # Threshold boundary: runway exactly at limit → alert
    m_boundary = {**m_healthy, "survival_runway_days": ALERT_THRESHOLDS["runway_critical_days"]}
    boundary_alerts = _generate_alerts(m_boundary)
    ok &= check("runway alert fires at exact threshold",
                any(a["type"] == "runway_critical" for a in boundary_alerts))

    return ok


# ── Test: top risk driver ordering ───────────────────────────────────────────

def test_top_risk_driver_ordering():
    print("\ntest_top_risk_driver_ordering")
    ok = True

    lights_mixed = {
        "survival_runway":       "amber",
        "real_cash_coverage":    "red",
        "fx_mismatch":           "green",
        "revenue_concentration": "red",
        "deterioration":         "amber",
    }
    metrics = {
        "survival_runway_days":  45,
        "real_cash_coverage":    0.8,
        "fx_mismatch_exposure":  0.05,
        "revenue_concentration": 0.85,
        "deterioration_index":   -0.05,
    }
    drivers = _top_risk_drivers(metrics, lights_mixed)

    ok &= check("at most 3 drivers returned",  len(drivers) <= 3)
    ok &= check("exactly 4 non-green drivers exist — top 3 returned", len(drivers) == 3)
    ok &= check("first driver is red",         drivers[0]["light"] == "red",
                f"got {drivers[0]['light']}")
    ok &= check("second driver is red",        drivers[1]["light"] == "red",
                f"got {drivers[1]['light']}")
    ok &= check("third driver is amber",       drivers[2]["light"] == "amber",
                f"got {drivers[2]['light']}")
    ok &= check("green metrics not in drivers",
                all(d["metric"] != "fx_mismatch_exposure" for d in drivers))

    return ok


# ── Test: merchant detail includes trend windows ──────────────────────────────

def test_merchant_detail_trend():
    print("\ntest_merchant_detail_trend")
    ok = True

    mp = MockProvider()
    lid = "a1b2c3d4-0004-0004-0004-000000000004"  # Panadería San Martín
    txs = mp.get_transactions(lid)
    detail = build_merchant_detail(lid, "Panadería San Martín", "gastronomia", "Banco Nación", txs)

    ok &= check("trend_windows key present",   "trend_windows" in detail)
    ok &= check("w30d window present",         "w30d" in detail.get("trend_windows", {}))
    ok &= check("w60d window present",         "w60d" in detail.get("trend_windows", {}))
    ok &= check("w90d window present",         "w90d" in detail.get("trend_windows", {}))

    w30 = detail["trend_windows"]["w30d"]
    ok &= check("w30d has survival_runway_days", "survival_runway_days" in w30)
    ok &= check("w30d has deterioration_index",  "deterioration_index"  in w30)

    return ok


# ── Test: escalation rule 1 — high-risk + overdue review ─────────────────────

def test_escalation_rule_overdue():
    print("\ntest_escalation_rule_overdue")
    ok = True

    # Minimal row that triggers rule 1
    row_overdue = {
        "action": "reduce_exposure",
        "review_overdue_days": 5,
        "alerts": [],
    }
    esc, reason = _compute_escalation(row_overdue, override=None)
    ok &= check("escalation fires for high-risk + overdue", esc)
    ok &= check("reason mentions overdue days", reason and "overdue" in reason.lower(),
                f"got: {reason}")

    # Rule should NOT fire for a low-risk merchant even if overdue
    row_low = {**row_overdue, "action": "monitor"}
    esc2, _ = _compute_escalation(row_low, override=None)
    ok &= check("monitor + overdue does NOT escalate", not esc2)

    # Rule should NOT fire for high-risk if review is not overdue
    row_current = {**row_overdue, "action": "review_now", "review_overdue_days": 0}
    esc3, _ = _compute_escalation(row_current, override=None)
    ok &= check("review_now + not overdue does NOT trigger rule 1", not esc3)

    return ok


# ── Test: escalation rule 2 — override on high-risk merchant ─────────────────

def test_escalation_rule_override():
    print("\ntest_escalation_rule_override")
    ok = True

    row_safe = {
        "action": "monitor",          # model currently at monitor
        "review_overdue_days": 0,
        "alerts": [],
    }
    override_from_high = {
        "original_recommendation": "reduce_exposure",
        "current_recommendation":  "monitor",
    }
    esc, reason = _compute_escalation(row_safe, override=override_from_high)
    ok &= check("override from high-risk original triggers escalation", esc)
    ok &= check("reason references original recommendation",
                reason and "reduce_exposure" in reason, f"got: {reason}")

    # Override where original was NOT high-risk → should not trigger rule 2
    override_from_low = {
        "original_recommendation": "healthy",
        "current_recommendation":  "reduce_exposure",
    }
    row_safe2 = {**row_safe, "action": "reduce_exposure"}
    esc2, _ = _compute_escalation(row_safe2, override=override_from_low)
    ok &= check("override from non-high-risk original does NOT trigger rule 2",
                not esc2,
                "rule 2 checks original_recommendation, not current action")

    return ok


# ── Test: escalation rule 3 — 2+ critical alerts ─────────────────────────────

def test_escalation_rule_critical_alerts():
    print("\ntest_escalation_rule_critical_alerts")
    ok = True

    two_critical = [
        {"type": "runway_critical",      "severity": "critical"},
        {"type": "coverage_insufficient","severity": "critical"},
    ]
    row = {"action": "healthy", "review_overdue_days": 0, "alerts": two_critical}
    esc, reason = _compute_escalation(row, override=None)
    ok &= check("2 critical alerts trigger escalation", esc)
    ok &= check("reason mentions critical alert count",
                reason and "critical" in reason.lower(), f"got: {reason}")

    one_critical = [{"type": "runway_critical", "severity": "critical"}]
    row2 = {**row, "alerts": one_critical}
    esc2, _ = _compute_escalation(row2, override=None)
    ok &= check("1 critical alert does NOT trigger rule 3", not esc2)

    one_crit_one_warning = [
        {"type": "runway_critical", "severity": "critical"},
        {"type": "fx_high",         "severity": "warning"},
    ]
    row3 = {**row, "alerts": one_crit_one_warning}
    esc3, _ = _compute_escalation(row3, override=None)
    ok &= check("1 critical + 1 warning does NOT trigger rule 3", not esc3)

    return ok


# ── Test: no escalation when no rules apply ───────────────────────────────────

def test_no_escalation():
    print("\ntest_no_escalation")
    ok = True

    row_clean = {
        "action":              "healthy",
        "review_overdue_days": 0,
        "alerts":              [{"type": "fx_high", "severity": "warning"}],
    }
    esc, reason = _compute_escalation(row_clean, override=None)
    ok &= check("no escalation for healthy, current, single-warning merchant", not esc)
    ok &= check("escalation_reason is None when no escalation", reason is None)

    return ok


# ── Test: portfolio escalation aggregates ─────────────────────────────────────

def test_portfolio_escalation_aggregates():
    print("\ntest_portfolio_escalation_aggregates")
    ok = True

    portfolio = build_portfolio(_make_all_merchants(with_review=True))

    ok &= check("escalated_count key present", "escalated_count" in portfolio)
    ok &= check("open_case_count key present",  "open_case_count"  in portfolio)
    ok &= check("deteriorating_by_sector key present",
                "deteriorating_by_sector" in portfolio)

    esc = portfolio["escalated_count"]
    opn = portfolio["open_case_count"]
    dbs = portfolio["deteriorating_by_sector"]

    ok &= check("escalated_count >= 1", esc >= 1, f"got {esc}")
    ok &= check("escalated_count <= merchant_count",
                esc <= portfolio["merchant_count"])

    ok &= check("open_case_count >= 0", opn >= 0, f"got {opn}")

    # Every escalated merchant must have needs_escalation=True and a reason
    for m in portfolio["merchants"]:
        if m["needs_escalation"]:
            ok &= check(f"{m['name'][:20]} has escalation_reason",
                        bool(m["escalation_reason"]))

    # deteriorating_by_sector values must all be negative (that's the filter)
    for sector, avg in dbs.items():
        ok &= check(f"{sector} avg det < 0", avg < 0, f"got {avg}")

    # Sectors in dbs must be a subset of sectors in the portfolio
    all_sectors = {m["sector"] for m in portfolio["merchants"]}
    for s in dbs:
        ok &= check(f"sector '{s}' exists in portfolio", s in all_sectors)

    return ok


# ── Test: case log events appear in merchant detail timeline ──────────────────

def test_case_log_in_timeline():
    print("\ntest_case_log_in_timeline")
    ok = True

    mp = MockProvider()
    # Verdulería La Fresca — has case log, override, and escalation
    lid = "a1b2c3d4-0010-0010-0010-000000000010"
    meta = MOCK_MERCHANTS_AR[lid]
    txs  = mp.get_transactions(lid)
    case_log = MOCK_CASE_LOG_AR.get(lid, [])

    detail = build_merchant_detail(
        lid, meta["name"], meta["sector"], meta["bank"], txs,
        review_state=MOCK_REVIEW_STATE_AR.get(lid),
        override=MOCK_OVERRIDES_AR.get(lid),
        case_log=case_log,
    )

    history   = detail["risk_history"]
    ev_types  = [e["event_type"] for e in history]

    ok &= check("risk_history is non-empty", len(history) > 0)
    ok &= check("override event present in timeline", "override" in ev_types)
    ok &= check("flag_raised event present",          "flag_raised" in ev_types)
    ok &= check("analyst_reviewed event present",     "analyst_reviewed" in ev_types)

    # All case events must carry a label field
    case_events = [e for e in history if e.get("event_type") in _CASE_EVENT_LABELS]
    for ev in case_events:
        ok &= check(f"case event '{ev['event_type']}' has label field",
                    bool(ev.get("label")))
        ok &= check(f"case event '{ev['event_type']}' label is human-readable string",
                    isinstance(ev.get("label"), str) and len(ev["label"]) > 3)

    # Override event must also have a label
    for ev in history:
        if ev.get("event_type") == "override":
            ok &= check("override event has label field", bool(ev.get("label")))

    # Timeline must be chronologically ordered (no decreasing dates)
    dates = [e["date"] for e in history]
    ok &= check("timeline is chronologically ordered",
                dates == sorted(dates), f"got: {dates}")

    # case_log key present and matches input
    ok &= check("case_log key on detail response", "case_log" in detail)
    ok &= check("case_log length matches input", len(detail["case_log"]) == len(case_log))

    return ok


# ── Test: timeline ordering with mixed event types ────────────────────────────

def test_timeline_ordering():
    print("\ntest_timeline_ordering")
    ok = True

    mp = MockProvider()
    # Fotocopias Rápidas — unreviewed, has case log with 3 events all on same date
    lid = "a1b2c3d4-0012-0012-0012-000000000012"
    meta = MOCK_MERCHANTS_AR[lid]
    txs  = mp.get_transactions(lid)
    case_log = MOCK_CASE_LOG_AR.get(lid, [])

    detail = build_merchant_detail(
        lid, meta["name"], meta["sector"], meta["bank"], txs,
        review_state=MOCK_REVIEW_STATE_AR.get(lid),
        override=MOCK_OVERRIDES_AR.get(lid),
        case_log=case_log,
    )

    history = detail["risk_history"]
    dates   = [e["date"] for e in history]
    ok &= check("Fotocopias timeline is sorted", dates == sorted(dates), str(dates))

    # override event present (model says review_now, analyst overrode to reduce_exposure)
    ok &= check("override event in Fotocopias timeline",
                any(e.get("event_type") == "override" for e in history))

    # all 6 case event types are defined in _CASE_EVENT_LABELS
    ok &= check("all 6 case event types defined",
                len(_CASE_EVENT_LABELS) == 6, str(list(_CASE_EVENT_LABELS)))

    return ok


# ── Test: FX signal increases fx_mismatch for FX-exposed merchants ────────────

def test_fx_signal_increases_fx_mismatch():
    print("\ntest_fx_signal_increases_fx_mismatch")
    ok = True

    mp = MockProvider()
    # Ferretería López — has USD tool imports → FX-exposed
    lid  = "a1b2c3d4-0005-0005-0005-000000000005"
    txs  = mp.get_transactions(lid)
    base = extract_argentina_features(txs)

    signal = get_external_signal(lid)
    ok &= check("signal has fx_adjustment_factor", "fx_adjustment_factor" in signal)
    ok &= check("factor > 1.0 for Ferretería (900→985)",
                signal["fx_adjustment_factor"] > 1.0,
                f"got {signal['fx_adjustment_factor']}")

    updated = apply_fx_signal(txs, base, signal)

    ok &= check("updated metrics is a dict", isinstance(updated, dict))
    ok &= check("updated has fx_mismatch_exposure", "fx_mismatch_exposure" in updated)
    ok &= check("fx_mismatch_exposure increased after rate shock",
                updated["fx_mismatch_exposure"] >= base["fx_mismatch_exposure"],
                f"base={base['fx_mismatch_exposure']}, updated={updated['fx_mismatch_exposure']}")

    # All other metrics must be unchanged
    for key in ("survival_runway_days", "real_cash_coverage",
                "revenue_concentration", "deterioration_index"):
        ok &= check(f"{key} unchanged after signal",
                    updated[key] == base[key],
                    f"base={base[key]}, updated={updated[key]}")

    return ok


# ── Test: FX signal has no effect on zero-FX merchants ────────────────────────

def test_fx_signal_no_effect_zero_fx():
    print("\ntest_fx_signal_no_effect_zero_fx")
    ok = True

    mp = MockProvider()
    # Panadería San Martín — no FX-denominated outflows
    lid  = "a1b2c3d4-0004-0004-0004-000000000004"
    txs  = mp.get_transactions(lid)
    base = extract_argentina_features(txs)

    signal  = get_external_signal(lid)
    updated = apply_fx_signal(txs, base, signal)

    ok &= check("fx_mismatch_exposure unchanged for no-FX merchant",
                updated["fx_mismatch_exposure"] == base["fx_mismatch_exposure"],
                f"base={base['fx_mismatch_exposure']}, updated={updated['fx_mismatch_exposure']}")

    for key in ("survival_runway_days", "real_cash_coverage",
                "revenue_concentration", "deterioration_index"):
        ok &= check(f"{key} unchanged after signal",
                    updated[key] == base[key])

    return ok


# ── Test: build_refresh_event produces correct timeline entry ─────────────────

def test_build_refresh_event():
    print("\ntest_build_refresh_event")
    ok = True

    mp = MockProvider()
    lid  = "a1b2c3d4-0005-0005-0005-000000000005"
    txs  = mp.get_transactions(lid)
    base = extract_argentina_features(txs)

    signal  = get_external_signal(lid)
    updated = apply_fx_signal(txs, base, signal)
    base_scored    = score_argentina(base)
    updated_scored = score_argentina(updated)

    event = build_refresh_event(
        signal, base, updated,
        base_scored["action"], updated_scored["action"]
    )

    ok &= check("event_type is agent_refresh",  event["event_type"] == "agent_refresh")
    ok &= check("label is correct",              event["label"] == "Agent Refresh (FX update)")
    ok &= check("event has date",                bool(event.get("date")))
    ok &= check("event has action",              bool(event.get("action")))
    ok &= check("event has reason",              bool(event.get("reason")))
    ok &= check("event has signal sub-dict",     isinstance(event.get("signal"), dict))
    ok &= check("reason mentions rate change",
                "ARS/USD" in event["reason"],
                f"reason: {event['reason'][:80]}")
    ok &= check("reason mentions fx mismatch",
                "mismatch" in event["reason"].lower(),
                f"reason: {event['reason'][:80]}")
    ok &= check("period field present",          bool(event.get("period")))

    return ok


# ── Test: recommendation change detected when FX push crosses threshold ────────

def test_refresh_recommendation_change_detection():
    print("\ntest_refresh_recommendation_change_detection")
    ok = True

    # Almacén El Toro — high FX, strong rate shock (900→960 ≈ 6.7%)
    mp  = MockProvider()
    lid = "a1b2c3d4-0006-0006-0006-000000000006"
    txs = mp.get_transactions(lid)
    base = extract_argentina_features(txs)

    signal  = get_external_signal(lid)
    updated = apply_fx_signal(txs, base, signal)

    base_action    = score_argentina(base)["action"]
    updated_action = score_argentina(updated)["action"]

    event = build_refresh_event(signal, base, updated, base_action, updated_action)

    if base_action == updated_action:
        ok &= check("reason says recommendation unchanged",
                    "unchanged" in event["reason"],
                    f"reason: {event['reason'][:100]}")
    else:
        ok &= check("reason notes recommendation changed",
                    "changed" in event["reason"],
                    f"reason: {event['reason'][:100]}")

    # Either way, the reason must mention the correct base and updated actions
    ok &= check("event action matches updated_action",
                event["action"] == updated_action,
                f"expected {updated_action}, got {event['action']}")

    return ok


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = [
        test_expected_actions(),
        test_portfolio_aggregation(),
        test_action_counts(),
        test_portfolio_aggregates(),
        test_alert_generation(),
        test_top_risk_driver_ordering(),
        test_merchant_detail_trend(),
        # Phase 2.7 — escalation and case log
        test_escalation_rule_overdue(),
        test_escalation_rule_override(),
        test_escalation_rule_critical_alerts(),
        test_no_escalation(),
        test_portfolio_escalation_aggregates(),
        test_case_log_in_timeline(),
        test_timeline_ordering(),
        # Phase 3 — FX signal refresh
        test_fx_signal_increases_fx_mismatch(),
        test_fx_signal_no_effect_zero_fx(),
        test_build_refresh_event(),
        test_refresh_recommendation_change_detection(),
    ]
    total  = len(results)
    passed = sum(results)
    print(f"\n{'='*45}")
    print(f"  {passed}/{total} test suites passed")
    print(f"{'='*45}")
    if passed < total:
        raise SystemExit(1)
