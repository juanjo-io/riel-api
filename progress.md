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

## Phase 3 — Merchant Detail
_Complete (merged into Phase 2)_

## Phase 4 — Connect Update
_Blocked on Phase 3_

## Phase 5 — x402 Refresh
_Future_

---

## Known Issues / Debt
- `@app.on_event("startup")` deprecated — should migrate to `lifespan`
- Belvo legacy endpoints (`/belvo-token`, `/create-widget-session`) still present, unused
- `main.py.bak` exists — clean up
- `/demo` route serves `demo.html` (Colombia-focused) — defer cleanup
- Magic-link email delivery is console-only (no SMTP yet)
- `dashboard_stats` requires both API key AND lender cookie — consider simplifying to cookie only
- Prometeo `environment='testing'` — confirm correct value for sandbox
