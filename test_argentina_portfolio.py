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
)
from argentina_config import ALERT_THRESHOLDS

_PASS = "\033[92m✓\033[0m"
_FAIL = "\033[91m✗\033[0m"

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {_PASS} {label}")
    else:
        print(f"  {_FAIL} {label}" + (f" — {detail}" if detail else ""))
    return condition


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_all_merchants():
    mp = MockProvider()
    return [
        {
            "link_id":      lid,
            "name":         meta["name"],
            "sector":       meta.get("sector", "other"),
            "bank":         meta.get("bank", ""),
            "transactions": mp.get_transactions(lid),
        }
        for lid, meta in MOCK_MERCHANTS_AR.items()
    ]


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
    ]
    total  = len(results)
    passed = sum(results)
    print(f"\n{'='*45}")
    print(f"  {passed}/{total} test suites passed")
    print(f"{'='*45}")
    if passed < total:
        raise SystemExit(1)
