# ── Traffic light thresholds ──────────────────────────────────────────────────
# The scorer reads these; do not hardcode comparisons elsewhere.
# Format: {"green": cutoff, "amber": cutoff}
# Directional convention stored in scorer._light() — not here.
THRESHOLDS = {
    "survival_runway_days":  {"green": 60,   "amber": 30},
    "real_cash_coverage":    {"green": 1.5,  "amber": 1.0},
    "fx_mismatch_exposure":  {"green": 0.10, "amber": 0.30},
    "revenue_concentration": {"green": 0.50, "amber": 0.70},
    "deterioration_index":   {"green": 0.10, "amber": -0.10},
}

# ── Action thresholds ─────────────────────────────────────────────────────────
DETERIORATION_REDUCE_THRESHOLD     = -0.30   # det < this → reduce_exposure (overrides red count)
DETERIORATION_OPPORTUNITY_THRESHOLD = 0.20   # det > this (all green) → opportunity

# ── Alert thresholds ─────────────────────────────────────────────────────────
ALERT_THRESHOLDS = {
    "runway_critical_days":  30,    # runway <= this → critical alert
    "coverage_critical":     1.0,   # coverage < this → critical alert
    "fx_high":               0.30,  # fx >= this → warning
    "concentration_high":    0.70,  # concentration >= this → warning
    "deterioration_severe": -0.30,  # deterioration <= this → critical
}

# ── Action metadata ───────────────────────────────────────────────────────────
ACTION_LABELS = {
    "opportunity":     "Opportunity — consider limit increase",
    "healthy":         "Healthy — no action needed",
    "monitor":         "Monitor — watch trend",
    "review_now":      "Review Now — schedule assessment",
    "reduce_exposure": "Reduce Exposure — act immediately",
}

ACTION_STATUS_COLORS = {
    "opportunity":     "teal",
    "healthy":         "green",
    "monitor":         "amber",
    "review_now":      "orange",
    "reduce_exposure": "red",
}

# ── FX detection keywords ─────────────────────────────────────────────────────
FX_KEYWORDS = {"usd", "dolar", "dolares", "eur", "euro", "euros"}

# ── Model metadata ─────────────────────────────────────────────────────────────
# Bump MODEL_NAME on any threshold or logic change so API consumers can track
# which version produced a given score.
#
# MODEL_NAME         — used by the batch scoring pipeline (unchanged thresholds + logic)
# REFRESH_MODEL_NAME — reported when a manual agent refresh applies an external FX signal.
#                      v0_3 uses the same thresholds and scoring rules as v0_2; the only
#                      difference is that fx_mismatch_exposure is recomputed using a live
#                      (mock in Phase 3 v0) FX rate rather than raw transaction amounts alone.
MODEL_NAME         = "riel_argentina_v0_2"
REFRESH_MODEL_NAME = "riel_argentina_v0_3"
LOOKBACK_WINDOWS   = [30, 60, 90]   # days; used for trend windows and history snapshots
REFRESH_MODE       = "batch"         # "batch" | "realtime"; batch = periodic full recompute

# ── Review cadence (days between reviews by risk state) ───────────────────────
REVIEW_CADENCE_DAYS = {
    "opportunity":     30,
    "healthy":         30,
    "monitor":         14,
    "review_now":      7,
    "reduce_exposure": 7,
}
