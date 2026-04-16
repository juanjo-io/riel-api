# Riél — Task List

## Phase 0 — Foundation
- [ ] P0-1: Write `argentina_features.py` — extract Survival Runway, Real Cash Coverage, FX Mismatch, Revenue Concentration, Deterioration Index from transactions
- [ ] P0-2: Write `argentina_scorer.py` — map 5 metrics to action: Healthy / Monitor / Review Now / Reduce Exposure / Opportunity
- [ ] P0-3: Add 3 Argentina mock merchant profiles to `mock_provider.py` (ARS, Argentine banks: Banco Nación, Galicia, Brubank)
- [ ] P0-4: Add `GET /argentina/score/{link_id}` endpoint in `main.py` (API-key gated)
- [ ] P0-5: Verify existing `/score` unchanged for all 3 Colombia mock profiles

## Phase 1 — Portfolio Monitoring Backend
- [ ] P1-1: Write SQL for `merchants` table in Supabase
- [ ] P1-2: Add `GET /portfolio` endpoint — list all merchants with current metrics + action
- [ ] P1-3: Add `GET /merchant/{id}/data` endpoint — single merchant full metrics + 30/60/90d trend
- [ ] P1-4: Update `_SEED_DATA` with Argentina merchants (replace Colombia names/banks/amounts)
- [ ] P1-5: Update startup seed to write Argentina metrics, not COP score
- [ ] P1-6: Verify `/portfolio` returns all 5 metrics per row

## Phase 2 — Dashboard UI
- [ ] P2-1: Replace KPI strip in `dashboard.html` with action distribution counts
- [ ] P2-2: Replace charts with sortable merchant table (columns: name, bank, each metric, action badge)
- [ ] P2-3: Add filter controls by action type
- [ ] P2-4: Verify auth still required, design system intact

## Phase 3 — Merchant Detail Page
- [ ] P3-1: Create `merchant.html` — metric breakdown + 30/60/90d sparklines per metric
- [ ] P3-2: Add `GET /merchant/{id}` route in `main.py` serving `merchant.html` (auth-gated)
- [ ] P3-3: Wire JS to `GET /merchant/{id}/data`
- [ ] P3-4: Add navigation: portfolio table row → merchant detail

## Phase 4 — Connect Flow Update
- [ ] P4-1: Update result screen in `connect.html` to show Argentina metrics + action
- [ ] P4-2: Update `POST /connect/score` to run Argentina pipeline
- [ ] P4-3: Verify mock connect flow end-to-end

## Phase 5 — x402 Refresh (Future)
- [ ] P5-1: Add `POST /merchant/{id}/refresh` with x402 challenge/response
- [ ] P5-2: Trigger fresh Prometeo pull + Argentina scorer
- [ ] P5-3: Return `{ metrics_before, metrics_after, action_changed, delta }`

## Ongoing
- [ ] Remove Belvo legacy endpoints (`/belvo-token`, `/create-widget-session`) after Phase 1
- [ ] Set up email delivery for magic links (currently console-only)
- [ ] Add `AUTH_SECRET_KEY`, `LENDER_EMAILS`, `SELF_BASE_URL` to Railway env docs
