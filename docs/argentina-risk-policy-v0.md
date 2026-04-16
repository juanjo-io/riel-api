# Argentina SMB Risk Policy — v0

**Model:** `riel_argentina_v0_2`
**Status:** Pilot / pre-outcome-data
**Scope:** Argentina informal-sector SMBs assessed via bank transaction history
**Maintainer:** Riél risk team
**Last updated:** 2026-04-16

---

## 1. Metrics

Five signals are extracted from the most recent 90 days of bank transaction data. All metrics are computed on a rolling basis using the reference date of the most recent transaction in the dataset.

### 1.1 Survival Runway (days)

**Definition:** Estimated number of days the business can sustain operations at current net cash burn, given the balance of contractual outflows and inflows.

**Formula:**
```
net_cash_30d     = sum of inflows − sum of outflows in last 30 days
contractual_out  = sum of outflows from counterparties appearing ≥2 times in 90d window
survival_runway  = account_balance / (contractual_out / 30)
                   clamped to [0, 999]
```

**Interpretation:** Higher is better. A value of 30 means the business has approximately one month of operating cash given its fixed obligations.

---

### 1.2 Real Cash Coverage (×)

**Definition:** Ratio of total cash inflows to contractual obligations over the last 30 days.

**Formula:**
```
real_cash_coverage = total_inflows_30d / contractual_outflows_30d
```
If contractual outflows are zero, coverage is set to 3.0 (above all thresholds).

**Interpretation:** Higher is better. A value of 1.0× means inflows exactly cover obligations. Below 1.0× means the business relies on reserves or new financing to meet recurring commitments.

---

### 1.3 FX Mismatch Exposure (%)

**Definition:** Fraction of total outflows in the last 30 days denominated in or referencing a foreign currency (USD, EUR).

**Formula:**
```
fx_outflows = outflows whose counterparty name contains any of:
              usd, dolar, dolares, eur, euro, euros (case-insensitive)
fx_mismatch_exposure = fx_outflows / total_outflows_30d
```
If total outflows are zero, exposure is set to 0.0.

**Interpretation:** Lower is better. A high FX mismatch means a large portion of the cost base is exposed to ARS depreciation risk.

---

### 1.4 Revenue Concentration (%)

**Definition:** Share of total inflows in the last 30 days attributable to the top 3 counterparties by volume.

**Formula:**
```
revenue_concentration = sum(top_3_inflow_counterparties) / total_inflows_30d
```
If total inflows are zero, concentration is set to 1.0 (worst case).

**Interpretation:** Lower is better. A value of 0.80 means 80% of revenue comes from just three sources, indicating high counterparty dependency.

---

### 1.5 Deterioration Index

**Definition:** Relative change in net cash flow (inflows minus outflows) between the most recent 30 days and the prior 30 days (days 31–60).

**Formula:**
```
net_30d    = total_inflows(last 30d) − total_outflows(last 30d)
net_31_60d = total_inflows(days 31–60) − total_outflows(days 31–60)

deterioration_index = (net_30d − net_31_60d) / |net_31_60d|
                      clamped to [−1.0, +1.0]
```
If `net_31_60d` is zero, the index is set to +0.5 (treated as improvement from a flat base).

**Interpretation:** Positive values indicate improving cash flow; negative values indicate deterioration. The index is symmetric around 0; a value of −0.30 means net cash flow declined 30% compared to the prior period.

---

## 2. Traffic-Light Thresholds

Each metric is assigned a traffic light (green / amber / red) using fixed thresholds. All thresholds are defined in `argentina_config.py`. The table below is authoritative; do not hardcode these values elsewhere.

| Metric | Green (no concern) | Amber (watch) | Red (action required) |
|---|---|---|---|
| Survival Runway | > 60 days | 30–60 days | < 30 days |
| Real Cash Coverage | > 1.5× | 1.0–1.5× | < 1.0× |
| FX Mismatch Exposure | < 10% | 10–30% | > 30% |
| Revenue Concentration | < 50% | 50–70% | > 70% |
| Deterioration Index | > +0.10 | −0.10 to +0.10 | < −0.10 |

**Direction convention:**
- Runway, Coverage, Deterioration: higher = better (green = high, red = low)
- FX Mismatch, Revenue Concentration: lower = better (green = low, red = high)

---

## 3. Risk State and Recommendation Mapping

The five traffic lights are combined into a single risk state (action) using the following rules, evaluated in priority order.

| Priority | Condition | Risk State | Recommendation Label |
|---|---|---|---|
| 1 (highest) | Deterioration index < −0.30 | `reduce_exposure` | Reduce Exposure — act immediately |
| 2 | ≥ 3 red lights | `reduce_exposure` | Reduce Exposure — act immediately |
| 3 | ≥ 2 red lights, or ≥ 1 red + ≥ 2 amber | `review_now` | Review Now — schedule assessment |
| 4 | ≥ 1 red, or ≥ 3 amber | `monitor` | Monitor — watch trend |
| 5 | All green + deterioration > +0.20 | `opportunity` | Opportunity — consider limit increase |
| 6 (default) | All green | `healthy` | Healthy — no action needed |

**Status colors** assigned to each risk state:

| Risk State | Color | Intended Use |
|---|---|---|
| `opportunity` | teal | Positive signal; candidate for limit increase |
| `healthy` | green | No action; portfolio is performing |
| `monitor` | amber | Heightened attention; flag for next review cycle |
| `review_now` | orange | Credit assessment required within the cycle |
| `reduce_exposure` | red | Immediate intervention; suspend new disbursements |

---

## 4. Alert Rules

Alerts are generated independently of the risk state. A merchant may carry warnings even if its overall risk state is `healthy` (e.g., FX exposure is elevated but other metrics are strong). Alert thresholds are defined in `ALERT_THRESHOLDS` in `argentina_config.py`.

| Alert Type | Severity | Trigger Condition |
|---|---|---|
| `runway_critical` | critical | Survival runway ≤ 30 days |
| `coverage_insufficient` | critical | Real cash coverage < 1.0× |
| `deterioration_severe` | critical | Deterioration index ≤ −0.30 |
| `fx_high` | warning | FX mismatch exposure ≥ 30% |
| `concentration_high` | warning | Revenue concentration ≥ 70% |

---

## 5. Calibration Roadmap

The current thresholds are set based on domain heuristics and operational judgment, not empirical outcome data. They should be treated as provisional until the following milestones are reached.

### Phase A — Label collection (target: 6 months post-pilot)

Collect actual repayment outcomes for all merchants that received a disbursement during the pilot. Record: disbursement date, amount, first missed payment (if any), days-to-default.

### Phase B — Threshold validation (target: 12 months post-pilot)

For each metric, compute the distribution of green/amber/red assignments against actual default and late-payment outcomes. Identify the threshold values that maximise the separation between defaulters and non-defaulters (e.g., using Kolmogorov-Smirnov distance or a simple ROC curve per metric).

Key questions to answer:
- Is the 30-day runway threshold too conservative or too lenient relative to observed defaults?
- Does the deterioration index add predictive value beyond runway alone?
- Are the FX and concentration thresholds calibrated to ARS volatility as of the pilot period?

### Phase C — Model versioning (ongoing)

Any change to threshold values, metric definitions, or the risk-state mapping rules must:

1. Increment `MODEL_NAME` in `argentina_config.py` (e.g., `v0_2` → `v0_3`).
2. Be documented in a versioned policy file (e.g., `docs/argentina-risk-policy-v0_3.md`).
3. Be reviewed by at least one risk stakeholder before deployment.
4. Preserve backward-compatibility in the API response: the `model.name` field in every portfolio and merchant response identifies which version produced the scores, enabling portfolio-level before/after comparisons.

### Known limitations of v0

- Thresholds are not segmented by industry sector. A panadería and a taller mecánico are assessed against the same runway cutoff; sector-specific calibration is deferred to v1.
- The deterioration index uses a single 30d vs 31–60d comparison. Businesses with seasonal revenue patterns may show spurious red signals. A seasonal-adjustment mechanism is deferred to v1.
- FX keyword matching is lexical (word-match against counterparty names). It will miss FX-denominated invoices whose counterparty names do not include currency keywords.
- No model decay monitoring is in place. Performance should be reviewed at the Phase B milestone.

---

## 6. Review Workflow

### 6.1 Review statuses

Each merchant row carries a `review_status` field managed by the lender's operations team:

| Status | Meaning |
|---|---|
| `unreviewed` | No analyst review has been recorded for this merchant |
| `in_review` | Review is currently open / in progress |
| `reviewed` | Review completed; analyst note on file |

### 6.2 Review cadence

Required review frequency is determined by the merchant's current risk state. The next review date is computed as `last_review_date + cadence_days`. If `last_review_date` is absent, the review is considered immediately overdue.

| Risk State | Cadence |
|---|---|
| `opportunity` | 30 days |
| `healthy` | 30 days |
| `monitor` | 14 days |
| `review_now` | 7 days |
| `reduce_exposure` | 7 days |

Cadence values are defined in `REVIEW_CADENCE_DAYS` in `argentina_config.py`.

### 6.3 Analyst overrides

A lender analyst may record a recommendation that differs from the model's output. Overrides are additive: the model's `action` field is never mutated, and the override is stored in a separate `override` object on the merchant row.

Override object fields:

| Field | Type | Description |
|---|---|---|
| `original_recommendation` | string | Model-derived action at time of override |
| `current_recommendation` | string | Analyst's amended recommendation |
| `override_reason` | string | Free-text rationale |
| `override_timestamp` | ISO datetime | When the override was recorded |
| `override_by` | string | Analyst identifier |

**Override semantics:** The model score and action are recomputed on every batch run and will reflect the latest transaction data regardless of any override in place. Overrides expire implicitly when the next batch run changes the model's recommendation — the override is preserved as a historical record but is no longer the "active" amendment if the model recommendation has changed.

Override events appear in the `risk_history` timeline with `event_type: "override"`.

### 6.4 Escalation rules

Escalation is computed automatically each batch run. A merchant is escalated (`needs_escalation: true`) when any of the following rules fire, evaluated in priority order:

| Priority | Rule | Escalation reason |
|---|---|---|
| 1 (highest) | High-risk action (`reduce_exposure` or `review_now`) **and** review is overdue | "High-risk merchant overdue for review by Nd" |
| 2 | Analyst override applied to a merchant whose original model recommendation was high-risk | "Analyst override active on high-risk merchant (original_action)" |
| 3 | Two or more critical alerts active simultaneously | "N critical alerts require immediate attention" |

Escalated merchants surface in the `escalated_count` portfolio aggregate and carry a `needs_escalation: true` / `escalation_reason: string` field on their row.

### 6.5 Case/action log

Each merchant may carry a `case_log` — a list of operational events recorded by analysts. Case events are merged into the `risk_history` timeline (with their own `event_type` values) so the full timeline is chronological.

Supported event types:

| Event type | Meaning |
|---|---|
| `flag_raised` | System or analyst flagged the merchant for review |
| `analyst_reviewed` | Analyst completed or contributed to a review |
| `recommendation_confirmed` | Credit committee or senior analyst confirmed the model recommendation |
| `no_action_taken` | Review concluded with no change to exposure or limit |
| `reduce_exposure_recommended` | Analyst confirmed or escalated to Reduce Exposure |
| `topup_candidate_flagged` | Merchant identified as candidate for limit increase |

Case events carry an optional `analyst` field (email of the responsible analyst) and a free-text `note`.

### 6.6 Portfolio-level aggregates

The portfolio response includes the following operational counters:

| Field | Definition |
|---|---|
| `unreviewed_count` | Number of merchants with `review_status == "unreviewed"` |
| `overdue_review_count` | Number of merchants where `review_overdue_days > 0` |
| `escalated_count` | Number of merchants where `needs_escalation == true` |
| `open_case_count` | High-risk merchants (`reduce_exposure` or `review_now`) whose review is not yet `"reviewed"` |
| `high_risk_by_sector` | Dict of sector → count for high-risk merchants, sorted descending by count |
| `deteriorating_by_sector` | Dict of sector → average deterioration index, for sectors averaging below −0.10, sorted worst-first |
