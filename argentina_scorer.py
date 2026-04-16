def score_argentina(metrics: dict) -> dict:
    """
    Map 5 Argentina risk metrics to an action recommendation.

    Thresholds
    ──────────
    survival_runway_days : green > 60  | amber 30–60 | red < 30
    real_cash_coverage   : green > 1.5 | amber 1.0–1.5 | red < 1.0
    fx_mismatch_exposure : green < 0.1 | amber 0.10–0.30 | red > 0.30
    revenue_concentration: green < 0.5 | amber 0.50–0.70 | red > 0.70
    deterioration_index  : green > 0.1 | amber -0.10–0.10 | red < -0.10

    Actions
    ───────
    reduce_exposure : ≥ 2 reds  OR  deterioration < -0.30
    review_now      : 1 red  OR  ≥ 2 ambers
    monitor         : exactly 1 amber
    opportunity     : all green AND deterioration > 0.20
    healthy         : all green
    """
    runway       = metrics.get("survival_runway_days", 0)
    coverage     = metrics.get("real_cash_coverage", 0.0)
    fx           = metrics.get("fx_mismatch_exposure", 0.0)
    concentration = metrics.get("revenue_concentration", 1.0)
    deterioration = metrics.get("deterioration_index", 0.0)

    def _light(metric, value):
        if metric == "runway":
            return "green" if value > 60 else ("amber" if value > 30 else "red")
        if metric == "coverage":
            return "green" if value > 1.5 else ("amber" if value >= 1.0 else "red")
        if metric == "fx":
            return "green" if value < 0.1 else ("amber" if value <= 0.3 else "red")
        if metric == "concentration":
            return "green" if value < 0.5 else ("amber" if value <= 0.7 else "red")
        if metric == "deterioration":
            return "green" if value > 0.1 else ("amber" if value >= -0.1 else "red")
        return "green"

    lights = {
        "survival_runway":      _light("runway",        runway),
        "real_cash_coverage":   _light("coverage",      coverage),
        "fx_mismatch":          _light("fx",            fx),
        "revenue_concentration": _light("concentration", concentration),
        "deterioration":        _light("deterioration", deterioration),
    }

    reds   = sum(1 for v in lights.values() if v == "red")
    ambers = sum(1 for v in lights.values() if v == "amber")

    if reds >= 2 or deterioration < -0.30:
        action = "reduce_exposure"
    elif reds == 1 or ambers >= 2:
        action = "review_now"
    elif ambers == 1:
        action = "monitor"
    elif deterioration > 0.20:
        action = "opportunity"
    else:
        action = "healthy"

    return {
        "action": action,
        "metric_lights": lights,
    }
