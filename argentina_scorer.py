from argentina_config import (
    THRESHOLDS,
    DETERIORATION_REDUCE_THRESHOLD,
    DETERIORATION_OPPORTUNITY_THRESHOLD,
)


def score_argentina(metrics: dict) -> dict:
    """
    Map 5 Argentina risk metrics to an action recommendation.
    Thresholds and action cutoffs live in argentina_config.py.

    Actions
    ───────
    reduce_exposure : ≥ 2 reds  OR  deterioration < DETERIORATION_REDUCE_THRESHOLD
    review_now      : 1 red  OR  ≥ 2 ambers
    monitor         : exactly 1 amber
    opportunity     : all green AND deterioration > DETERIORATION_OPPORTUNITY_THRESHOLD
    healthy         : all green
    """
    runway        = metrics.get("survival_runway_days", 0)
    coverage      = metrics.get("real_cash_coverage", 0.0)
    fx            = metrics.get("fx_mismatch_exposure", 0.0)
    concentration = metrics.get("revenue_concentration", 1.0)
    deterioration = metrics.get("deterioration_index", 0.0)

    def _light(key, value):
        t = THRESHOLDS[key]
        if key in ("survival_runway_days", "real_cash_coverage", "deterioration_index"):
            # Higher is better
            return "green" if value > t["green"] else ("amber" if value >= t["amber"] else "red")
        else:
            # Lower is better (fx, concentration)
            return "green" if value < t["green"] else ("amber" if value <= t["amber"] else "red")

    lights = {
        "survival_runway":       _light("survival_runway_days",  runway),
        "real_cash_coverage":    _light("real_cash_coverage",    coverage),
        "fx_mismatch":           _light("fx_mismatch_exposure",  fx),
        "revenue_concentration": _light("revenue_concentration", concentration),
        "deterioration":         _light("deterioration_index",   deterioration),
    }

    reds   = sum(1 for v in lights.values() if v == "red")
    ambers = sum(1 for v in lights.values() if v == "amber")

    if reds >= 2 or deterioration < DETERIORATION_REDUCE_THRESHOLD:
        action = "reduce_exposure"
    elif reds == 1 or ambers >= 2:
        action = "review_now"
    elif ambers == 1:
        action = "monitor"
    elif deterioration > DETERIORATION_OPPORTUNITY_THRESHOLD:
        action = "opportunity"
    else:
        action = "healthy"

    return {
        "action": action,
        "metric_lights": lights,
    }
