# Riél — Refactor Progress

## Status: Phase 0 not started

---

## Completed (pre-refactor baseline)

### Infrastructure
- [x] FastAPI app with CORS, Uvicorn, Railway deploy
- [x] Supabase client with in-memory fallback (`score_history`, `webhooks`, `api_keys`)
- [x] API key auth via `verify_api_key` (Supabase + env fallback)
- [x] Magic-link lender auth (`/lender/login-request`, `/lender/magic-login`, `/lender/logout`)
- [x] `get_current_lender` cookie dependency guards `/dashboard`
- [x] RLS enabled on Supabase tables (service_role only)
- [x] `SELF_BASE_URL` set in Railway → magic links use correct host

### Scoring Pipeline (Colombia, COP)
- [x] `features.py` — 6 signals from transactions
- [x] `scorer.py` — weighted 0–100 score → approve/review/decline
- [x] `MockProvider` — 3 deterministic Colombia profiles
- [x] `PrometeoProvider` — REST-based httpx wrapper, sandbox tested
- [x] `POST /score` (API-key gated)
- [x] `GET /score/{id}/explain` (API-key gated)
- [x] `POST /connect/score` (env-driven mock/prometeo)

### Dashboard
- [x] `dashboard.html` — warm off-white design, Chart.js 4
- [x] `GET /dashboard` (lender auth gated)
- [x] `GET /dashboard/stats` (lender auth + API key gated)
- [x] 18 mock merchants seeded at startup

### Webhooks
- [x] `POST /webhooks`, `GET /webhooks`, `DELETE /webhooks/{id}`, `POST /webhooks/test`
- [x] Webhook delivery on score change (delta ≥15 or bucket change)
- [x] Supabase persistence with in-memory fallback

### Connect Flow
- [x] `connect.html` — 5-screen bank-linking SPA
- [x] Warm off-white + teal design system
- [x] Argentina-ready UI (bank grid has CO + MX banks; needs AR banks)

### x402 Infrastructure
- [x] `_make_challenge_id` / `_verify_challenge_id` HMAC-SHA256
- [x] `GET /data/transactions` — 402 gated

---

## Phase 0 — Foundation
_Complete_

- [x] `argentina_features.py` — Survival Runway, Real Cash Coverage, FX Mismatch, Revenue Concentration, Deterioration Index
- [x] `argentina_scorer.py` — maps metrics to healthy/monitor/review_now/reduce_exposure/opportunity
- [x] Argentina mock merchants in `MockProvider` (Panadería→opportunity, Ferretería→monitor, Almacén→reduce_exposure)
- [x] `GET /argentina/score/{link_id}` (API-key gated)

## Phase 1 — Portfolio Backend
_Complete_

- [x] `argentina_config.py` — single source for all thresholds, action labels, status colours, FX keywords
- [x] `argentina_scorer.py` — imports thresholds from config (no hardcoding)
- [x] `argentina_features.py` — FX_KEYWORDS from config; added `extract_argentina_features_window()`
- [x] Mock merchants expanded 3 → 10 (varied sectors, 2× each of all 5 actions)
- [x] `argentina_portfolio.py` — `build_portfolio()`, `build_merchant_row()`, `build_merchant_detail()`, alerts, risk drivers
- [x] `GET /argentina/portfolio` (API-key gated)
- [x] `GET /argentina/merchant/{link_id}/data` — full metrics + 30/60/90d trend windows
- [x] `test_argentina_portfolio.py` — 7 test suites, all passing
- [ ] P1-1: Supabase `merchants` table SQL — **deferred** (portfolio reads from mock data; DB table not needed until live Prometeo data)
- [ ] P1-4/P1-5: _SEED_DATA → Argentina — **deferred** to Phase 2 (existing _SEED_DATA powers `/dashboard/stats`; replacing it breaks nothing but is cosmetic until the dashboard UI is rebuilt)

## Phase 2 — Dashboard UI
_Complete_

- [x] `dashboard.html` — replaced Colombia charts with Argentina-first portfolio watchlist
  - KPI strip: clickable action-count cards (reduce_exposure→opportunity, sorted by urgency)
  - Alerts panel: critical alerts surfaced above watchlist
  - Watchlist table: sector/action filters, sort by runway/coverage/FX%/trend
  - Columns: name+bank, sector, risk state badge, runway, coverage, FX%, trend arrow+index, top risk driver
  - Fetches from `GET /dashboard/portfolio` (cookie-only)
  - No Chart.js
- [x] `merchant.html` — new single-merchant drill-down page
  - Banner: name, sector, bank, risk state badge, action label, disabled "Refresh Risk" button
  - Narrative: auto-generated "what changed" text from deterioration_index + top risk driver
  - 5 metric cards with traffic-light border and dot
  - 30/60/90d trend table
  - Active alerts section
  - Improvement scenarios panel (distance to next threshold per amber/red metric)
- [x] `main.py` — 3 new routes:
  - `GET /dashboard/portfolio` (lender cookie only) → `build_portfolio()`
  - `GET /dashboard/merchant/{link_id}` (lender cookie only) → `build_merchant_detail()`
  - `GET /merchant/{link_id}` (lender cookie gated) → serves `merchant.html`

## Phase 2.5 — Threshold Transparency + Model Metadata
_Complete_

- [x] `argentina_config.py` — added `MODEL_NAME`, `LOOKBACK_WINDOWS`, `REFRESH_MODE`, `REVIEW_CADENCE_DAYS`
- [x] `argentina_portfolio.py` — model metadata in all responses; migration stats (improved/deteriorated/new_high_risk_30d); `_build_risk_history()` windowed audit trail
- [x] `dashboard.html` — model metadata line; portfolio summary panel (30d migration stats)
- [x] `merchant.html` — model metadata line in banner; risk history timeline section
- [x] `docs/argentina-risk-policy-v0.md` — full policy doc (metric definitions, threshold tables, risk-state mapping, alert rules, calibration roadmap, known limitations)

## Phase 2.6 — Review Workflow + Overrides
_Complete_

- [x] `argentina_config.py` — `REVIEW_CADENCE_DAYS` (opportunity/healthy→30d, monitor→14d, review_now/reduce_exposure→7d)
- [x] `providers/mock_provider.py` — `MOCK_REVIEW_STATE_AR` (10 merchants, mix of statuses, some overdue); `MOCK_OVERRIDES_AR` (2 overrides: Verdulería model=reduce_exposure→analyst=monitor; Fotocopias model=review_now→analyst=reduce_exposure)
- [x] `argentina_portfolio.py` — `_review_fields()` helper; `build_merchant_row()` adds review fields; `build_portfolio()` adds `unreviewed_count`, `overdue_review_count`, `high_risk_by_sector`; `build_merchant_detail()` injects override event into timeline
- [x] `main.py` — `dashboard_portfolio` and `dashboard_merchant` routes inject review_state + overrides
- [x] `dashboard.html` — ops summary panel (unreviewed/overdue); review indicator in Risk/Recommendation table cell
- [x] `merchant.html` — review status card (status badge, owner, next review date, overdue flag, analyst note); override section; override events in timeline with italic styling
- [x] `docs/argentina-risk-policy-v0.md` — Section 6 (review workflow, cadence rules, override semantics, portfolio aggregates)

## Phase 2.7 — Escalations + Case Log
_Complete_

### What changed

**Backend**

- `providers/mock_provider.py` — added `MOCK_CASE_LOG_AR`: per-merchant case event lists for 5 merchants (Panadería topup, Librería seasonal slump, Verdulería override, Fotocopias field-visit escalation, Indumentaria topup). 6 event types: `flag_raised`, `analyst_reviewed`, `recommendation_confirmed`, `no_action_taken`, `reduce_exposure_recommended`, `topup_candidate_flagged`.

- `argentina_portfolio.py`:
  - Added `_CASE_EVENT_LABELS` dict (6 event type → human-readable label mappings)
  - Added `_compute_escalation(row, override)` — 3 priority rules: (1) high-risk + overdue review, (2) analyst override on originally-high-risk merchant, (3) ≥2 critical alerts
  - Added `_SECTOR_DET_THRESHOLD = -0.10` local constant
  - `build_merchant_row()` now appends `needs_escalation: bool` and `escalation_reason: str | None`
  - `_build_risk_history()` now emits `event_type: "state"` and `label` on every snapshot entry
  - Override timeline entries now carry `label: "Analyst Override"`
  - Case log entries merged into timeline with `label` from `_CASE_EVENT_LABELS`
  - `build_portfolio()` adds `escalated_count`, `open_case_count`, `deteriorating_by_sector`
  - `build_merchant_detail()` accepts `case_log` param; merges into timeline; returns `case_log` key

- `main.py`:
  - Both dashboard routes (`/dashboard/portfolio`, `/dashboard/merchant/{link_id}`) now instantiate `MockProvider()` directly rather than calling `get_provider()`. **Reason:** Argentina dashboard data is always mock-backed; using `get_provider()` caused the Prometeo provider to be selected when `DATA_PROVIDER=prometeo`, returning empty transactions and scoring all merchants as `reduce_exposure` (0-day runway).
  - `MOCK_CASE_LOG_AR` threaded into `dashboard_merchant`

**Frontend**

- `dashboard.html`:
  - Added `.escalation-flag` CSS (red pill badge)
  - `renderOpsPanel()` extended: escalated count, open case count, highest-deteriorating sector (avg deterioration index)
  - `renderTable()`: escalated merchants show `ESCALATED` badge inline in the name cell

- `merchant.html`:
  - Added `.escalation-card` CSS (red-tinted card) and `.case-event` timeline CSS (gray dot)
  - Added `renderEscalation(d)` — renders escalation card with reason; skipped when not escalated
  - `render()` pipeline: `renderBanner → renderReviewCard → renderEscalation → renderOverride → ...`
  - `renderRiskHistory()` extended: handles all 6 case event types with `CASE_EVENT_LABELS` map, gray dot, optional analyst sub-line; override events remain amber/italic

**Tests** (`test_argentina_portfolio.py`)

- 7 existing suites preserved and passing
- 7 new suites added:
  - `test_escalation_rule_overdue` — rule 1 fires/doesn't fire correctly
  - `test_escalation_rule_override` — rule 2 checks `original_recommendation`, not current action
  - `test_escalation_rule_critical_alerts` — rule 3 requires ≥2 critical (not just any alerts)
  - `test_no_escalation` — clean merchant produces `needs_escalation=False, reason=None`
  - `test_portfolio_escalation_aggregates` — `escalated_count`, `open_case_count`, `deteriorating_by_sector` shape/values
  - `test_case_log_in_timeline` — case events appear in timeline with `label` field; timeline is sorted
  - `test_timeline_ordering` — mixed event types remain chronological; all 6 case event types defined
- **Total: 14/14 passing**

**Docs** — `docs/argentina-risk-policy-v0.md` extended with:
- Section 6.4: Escalation rules (priority table)
- Section 6.5: Case/action log event type definitions
- Section 6.6: Updated portfolio aggregates table (adds `escalated_count`, `open_case_count`, `deteriorating_by_sector`)

### Assumptions

- "Open case" is defined as: high-risk action (`reduce_exposure` or `review_now`) with `review_status != "reviewed"`. This is computed from existing fields, not a new flag.
- Escalation rule 2 checks `original_recommendation` from the override dict (not the current `action`) so that overrides applied to genuinely high-risk merchants still surface even when the analyst has brought the visible recommendation down.
- `deteriorating_by_sector` uses a -0.10 threshold (amber level) averaged across all merchants in the sector. Only sectors whose portfolio average falls below this are included.
- Dashboard routes pin to `MockProvider()` directly. The `DATA_PROVIDER` env var continues to govern all other routes (`/score`, `/argentina/score`, etc.).

### Follow-up recommendations for next phase

1. **Persistent case log** — `MOCK_CASE_LOG_AR` is demo-only. Production needs a `case_events` table (merchant_id, date, event_type, note, analyst, created_at). The `build_merchant_detail()` signature already accepts `case_log: list` so the route-layer change will be minimal.

2. **Escalation notification** — escalated merchants are currently surfaced visually only. A follow-up phase could add email/Slack dispatch (webhook-style) when `needs_escalation` flips from False → True between batch runs.

3. **Override expiry** — overrides don't have a TTL. If a batch run changes the model recommendation, the override silently loses meaning. Consider adding `expires_at` or a flag to mark stale overrides.

4. **Sector-level calibration** — `deteriorating_by_sector` is useful but currently uses a flat -0.10 threshold across all sectors. Seasonal sectors (e.g., librería) will naturally dip in off-peak months. Sector-aware baselines deferred to v1 per the policy doc.

5. **`/argentina/merchant/{link_id}/data` parity** — the API-key-protected endpoint doesn't yet pass `case_log`. Low priority (internal endpoint) but worth aligning before external consumers use it.

---

## Phase 3 — x402-style Refresh Risk (FX signal)
_Complete_

### What changed

**New file**

- `argentina_signals.py` — three functions:
  - `get_external_signal(link_id)` — returns a deterministic mock `fx_rate_snapshot` signal (no live API call). Per-merchant rates: Ferretería 900→985, Almacén 900→960, Librería 900→935; default 900→920.
  - `apply_fx_signal(txs, base_metrics, signal)` — re-extracts FX outflows from the 90d window, inflates by `fx_adjustment_factor`, recomputes `fx_mismatch_exposure`. All other metrics carried from `base_metrics` unchanged. Returns `base_metrics.copy()` when merchant has no FX exposure.
  - `build_refresh_event(signal, base_metrics, updated_metrics, base_action, updated_action)` — assembles an `agent_refresh` timeline entry with a three-part reason string: rate change, metric change (or "no impact"), recommendation change (or "unchanged").

**Backend**

- `argentina_config.py` — added `REFRESH_MODEL_NAME = "riel_argentina_v0_3"` with comment explaining v0_2 = batch, v0_3 = batch + external-signal refresh.
- `main.py` — new `POST /argentina/merchant/{link_id}/refresh` endpoint (lender cookie auth):
  1. Fetches transactions via `MockProvider()`
  2. Computes base metrics + score
  3. Fetches signal via `get_external_signal(link_id)`
  4. Recomputes `apply_fx_signal(txs, base_metrics, signal)`
  5. Re-scores updated metrics
  6. Builds full `build_merchant_detail()` response (with review state, override, case log)
  7. Patches `fx_mismatch_exposure` and updates `action`/`metric_lights`/`action_label`/`status_color` if action changed
  8. Appends `agent_refresh` event to `risk_history` (sorted by date)
  9. Stamps `model.name = REFRESH_MODEL_NAME` and `last_signal = signal`

**Frontend**

- `merchant.html`:
  - Refresh button enabled: teal accent border/color, hover fills teal, disabled shows 45% opacity.
  - `.refresh-error` CSS class (red, right-aligned, 13px).
  - `.timeline-item.agent-refresh` CSS: accent-colored dot and action label.
  - `renderBanner()`: button `onclick="refreshRisk()"` with `id="refresh-btn"`; hint text updated; `#refresh-error` div added.
  - `refreshRisk()` async function: POST to `/argentina/merchant/{link_id}/refresh`, show loading state, call `render(data)` on success, scroll to `.risk-history-section`, show error on failure with re-enabled button.
  - `renderRiskHistory()`: `isAgentRefresh` branch handles `agent_refresh` event_type; uses accent color, `.agent-refresh` item class, `entry.label` for display.
  - Risk history section wrapped in `<div class="risk-history-section">` for scroll target.

**Tests** (`test_argentina_portfolio.py`)

- 4 new suites (18/18 total passing):
  - `test_fx_signal_increases_fx_mismatch` — signal factor > 1, FX-exposed merchant shows higher ratio, all other metrics unchanged.
  - `test_fx_signal_no_effect_zero_fx` — no-FX merchant (Panadería) is unaffected by signal.
  - `test_build_refresh_event` — event_type, label, date, action, reason, signal sub-dict, ARS/USD and mismatch mentions, period field.
  - `test_refresh_recommendation_change_detection` — reason correctly says "unchanged" or "changed" based on action delta; `event.action` matches `updated_action`.

**Docs**

- `docs/argentina-risk-policy-v0.md` — Section 7: Agentic Refresh. Covers v0_2 vs v0_3 comparison table, signal specification, FX recomputation formula, timeline event schema, governance rules, and known limitations.

### Assumptions

- Refresh endpoint is lender-cookie-authenticated (same as `/dashboard/merchant`). No API key required.
- Refresh result is not persisted — a page reload returns to the batch score.
- Signal source is mock-only in v0. Production requires replacing `get_external_signal()` body; all downstream functions (`apply_fx_signal`, `build_refresh_event`) are source-agnostic.
- Only `fx_mismatch_exposure` is recomputed. Macro stress level is included in the signal but does not affect other metrics.

### Follow-up recommendations

1. **Signal persistence** — refresh results are ephemeral. A production deployment should write the refresh event to a `risk_events` table so it survives page reloads.
2. **Rate limiting** — no per-lender cooldown on the refresh endpoint. Add a 1-refresh-per-merchant-per-hour guard before exposing to external consumers.
3. **Live FX source** — replace `get_external_signal()` with a real source (BCRA official rate, Dolarito, or x402-gated aggregator). The `apply_fx_signal()` signature is source-agnostic.
4. **Multi-signal support** — currently only `fx_rate_snapshot`. Adding macro stress or sector-level signals requires a new `apply_*` function and a policy update.

---

## Phase 3.1 — Refresh Risk UX fix
_Complete_

- `merchant.html` — Refresh Risk button confirmed enabled (no `disabled` attribute); helper text updated to: _"Refresh risk uses an updated FX rate to recompute FX mismatch and risk; current view is from the last batch run."_
- No backend logic changes.

---

## Phase 4 — Connect Update
_Blocked_

## Phase 5 — x402 Refresh
_Superseded by Phase 3 (manual refresh implemented without full x402 flow)_

---

## Known Issues / Debt
- `@app.on_event("startup")` deprecated — should migrate to `lifespan`
- Belvo legacy endpoints (`/belvo-token`, `/create-widget-session`) still present, unused
- `main.py.bak` exists — clean up
- `/demo` route serves `demo.html` (Colombia-focused) — defer cleanup
- Magic-link email delivery is console-only (no SMTP yet)
- `dashboard_stats` requires both API key AND lender cookie — consider simplifying to cookie only
- Prometeo `environment='testing'` — confirm correct value for sandbox
- `/argentina/merchant/{link_id}/data` doesn't pass `case_log` (API-key endpoint, not dashboard)
